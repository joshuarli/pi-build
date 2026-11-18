import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import intercom


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
