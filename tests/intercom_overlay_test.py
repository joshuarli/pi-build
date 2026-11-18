import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import intercom
from tools.vendor import git_blob_sha


class IntercomOverlayTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(dir=".work/tmp")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.destination = self.root / ".work" / "prepared"
        self.destination.mkdir(parents=True)
        files = {
            "patches/intercom-tailnet-policy.patch": b"first review",
            "patches/intercom-tailnet-transport.patch": b"second review",
            "overlays/z.txt": b"final overlay",
            "overlays/docs/topics/a.md": b"first overlay",
        }
        for name, contents in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

    def test_digest_binds_the_ordered_patch_paths_and_bytes(self):
        expected = (
            b"patches/intercom-tailnet-policy.patch\0first review\0"
            b"patches/intercom-tailnet-transport.patch\0second review\0"
            b"overlays/docs/topics/a.md\0first overlay\0overlays/z.txt\0final overlay\0"
        )
        self.assertEqual(intercom.digest(self.root), hashlib.sha256(expected).hexdigest())
        first = self.root / "overlays/docs/topics/a.md"
        first.rename(first.with_name("b.md"))
        self.assertNotEqual(intercom.digest(self.root), hashlib.sha256(expected).hexdigest())

    def test_apply_dispatches_exact_patches_and_materializes_overlays(self):
        with patch.object(intercom.subprocess, "run") as execute:
            intercom.apply(self.destination, self.root)
        command = ["patch", "--batch", "--forward", "--fuzz=0", "-p1"]
        self.assertEqual(execute.call_args_list, [
            call(command, input=b"first review", cwd=self.destination, check=True),
            call(command, input=b"second review", cwd=self.destination, check=True),
        ])
        files = {path.relative_to(self.destination).as_posix(): path.read_bytes()
                 for path in self.destination.rglob("*") if path.is_file()}
        self.assertEqual(files, {"docs/topics/a.md": b"first overlay", "z.txt": b"final overlay"})

    def test_unsafe_destination_is_refused_before_applying_patches(self):
        outside = self.root / "sources"
        outside.mkdir()
        with (
            patch.object(intercom.subprocess, "run") as execute,
            self.assertRaisesRegex(ValueError, r"^Intercom changes may only be applied to a copied tree under \.work$"),
        ):
            intercom.apply(outside, self.root)
        execute.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

        with self.assertRaisesRegex(ValueError, "^destination already exists:"):
            intercom.prepare(self.destination, self.root)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_apply_requires_an_existing_destination(self):
        missing = self.destination / "missing"
        with (
            patch.object(intercom, "inputs", side_effect=AssertionError("read overlay inputs")),
            self.assertRaises(FileNotFoundError),
        ):
            intercom.apply(missing, self.root)
        self.assertFalse(missing.exists())

    def test_prepare_and_apply_keep_the_snapshot_root_out_of_scope(self):
        root = self.root / "verify-placement"
        snapshot = root / "sources"
        snapshot.mkdir(parents=True)
        (root / ".work").symlink_to(snapshot, target_is_directory=True)
        with (
            patch.object(intercom, "inputs", side_effect=AssertionError("read overlay inputs")),
            self.assertRaisesRegex(ValueError, r"^Intercom changes may only be applied to a copied tree under \.work$"),
        ):
            intercom.apply(snapshot, root)
        self.assertEqual(list(snapshot.iterdir()), [])

    def test_apply_refuses_to_replace_a_copied_source_file(self):
        existing = self.destination / "docs/topics/a.md"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"existing source")
        with (
            patch.object(intercom.subprocess, "run"),
            self.assertRaises(ValueError) as raised,
        ):
            intercom.apply(self.destination, self.root)
        self.assertEqual(str(raised.exception), f"Intercom overlay would replace an upstream file: {existing}")
        self.assertEqual(existing.read_bytes(), b"existing source")

    def test_missing_patch_is_rejected_by_the_digest_reader(self):
        (self.root / "patches/intercom-tailnet-policy.patch").unlink()
        with self.assertRaisesRegex(ValueError, "^Intercom patches and overlays must be regular files$"):
            intercom.digest(self.root)


    def test_prepare_materializes_only_verified_snapshot_files(self):
        name = "agent-intercom-core"
        source = self.root / "sources" / name
        source.mkdir(parents=True)
        original = b"export const value = 1;\n"
        script = source / "index.ts"
        script.write_bytes(original)
        (source / "notes.txt").write_bytes(b"outside inventory")
        manifest = source.parent / "upstreams.json"
        manifest.write_text(json.dumps({"sources": {name: {
            "path": f"sources/{name}", "sha": "a" * 40, "files": {"index.ts": git_blob_sha(original)},
        }}}))
        prepared = self.destination / "prepared"

        with (
            patch.object(sys, "path", list(sys.path)),
            patch.object(intercom.subprocess, "run") as execute,
        ):
            intercom.prepare(prepared, self.root)
            self.assertEqual(sys.path[0], str(self.root))
            self.assertEqual(execute.call_count, 2)
            self.assertEqual((prepared / name / "index.ts").read_bytes(), original)
            self.assertFalse((prepared / name / "notes.txt").exists())
            self.assertEqual((prepared / "docs/topics/a.md").read_bytes(), b"first overlay")

            execute.reset_mock()
            script.write_bytes(b"changed")
            rejected = self.destination / "rejected"
            with self.assertRaisesRegex(ValueError, r"changed=\['index\.ts'\]"):
                intercom.prepare(rejected, self.root)
            execute.assert_not_called()
            self.assertFalse(rejected.exists())

    def test_prepare_rejects_the_work_root_and_paths_outside_it(self):
        for destination in (self.root / ".work", self.root / "elsewhere"):
            with (
                self.subTest(destination=destination),
                self.assertRaisesRegex(ValueError, r"^prepared Intercom sources must be under \.work$"),
            ):
                intercom.prepare(destination, self.root)

    def test_cli_selects_the_requested_overlay_operation(self):
        for command in ("apply", "prepare", "digest"):
            args = ["intercom.py", command]
            if command != "digest":
                args.append(str(self.destination))
            with (
                self.subTest(command=command),
                patch.object(sys, "argv", args),
                patch.object(intercom, "apply") as apply,
                patch.object(intercom, "prepare") as prepare,
                patch.object(intercom, "digest", return_value="reviewed digest") as digest,
                redirect_stdout(io.StringIO()) as output,
            ):
                intercom.main()
                for name, operation in (("apply", apply), ("prepare", prepare), ("digest", digest)):
                    if name != command:
                        operation.assert_not_called()
                    elif name == "digest":
                        operation.assert_called_once_with()
                    else:
                        operation.assert_called_once_with(self.destination)
                self.assertEqual(output.getvalue(), "reviewed digest\n" if command == "digest" else "")


    def test_cli_prints_help_and_requires_an_operation(self):
        with (
            patch.object(sys, "argv", ["intercom.py", "--help"]),
            redirect_stdout(io.StringIO()) as output,
            self.assertRaises(SystemExit) as exited,
        ):
            intercom.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertIn("reviewed Intercom changes to a verified, disposable source tree", output.getvalue())

        with (
            patch.object(sys, "argv", ["intercom.py"]),
            redirect_stderr(io.StringIO()) as errors,
            self.assertRaises(SystemExit) as exited,
        ):
            intercom.main()
        self.assertEqual(exited.exception.code, 2)
        self.assertIn("the following arguments are required: command", errors.getvalue())
