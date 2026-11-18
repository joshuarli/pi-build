import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import vendor


class VendorUpdateTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(dir=".work/tmp")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.manifest = self.root / "sources/upstreams.json"
        self.names = ("pi-subagents", "agent-intercom-core")
        sources: dict[str, object] = {}
        self.raw = {"schema": 1, "opaque": {"kept": [2]}, "sources": sources}
        for name in self.names:
            source = self.root / "sources" / name
            source.mkdir(parents=True)
            package = b'{"version":"1.0.0"}\n'
            (source / "package.json").write_bytes(package)
            sources[name] = {
                "path": f"sources/{name}", "repository": f"example/{name}", "sha": "a" * 40,
                "ref": "main", "version": "1.0.0", "files": {"package.json": vendor.git_blob_sha(package)},
            }
        self.manifest.write_text(json.dumps(self.raw))
        self.original = self.snapshot()
        self.references = []
        self.clones = []
        self.enterContext(patch.object(vendor, "ROOT", self.root))
        self.enterContext(patch.object(vendor, "MANIFEST", self.manifest))

    def snapshot(self) -> dict[str, bytes]:
        sources = self.root / "sources"
        return {path.relative_to(sources).as_posix(): path.read_bytes() for path in sources.rglob("*") if path.is_file()}

    def manifest_data(self) -> vendor.Manifest:
        raw = vendor.object_mapping(json.loads(self.manifest.read_text()))
        return vendor.Manifest(raw, vendor.parse_sources(raw))

    def staged_command(self, *args: str, cwd: Path | None = None) -> str:
        if args[:2] == ("git", "status"):
            self.assertEqual(cwd, self.root)
            self.assertEqual(args[2:], ("--porcelain", "--", "sources"))
            return ""
        if args[:2] == ("git", "clone"):
            self.assertEqual(args[2:6], ("--quiet", "--depth=1", "--filter=blob:none", "--branch"))
            checkout = Path(args[-1])
            self.assertEqual(checkout.parent.parent, self.root / "sources")
            name = checkout.name.removesuffix("-checkout")
            self.clones.append(name)
            self.references.append(args[args.index("--branch") + 1])
            checkout.mkdir()
            (checkout / "package.json").write_bytes(b'{"version":"2.0.0"}\n')
            (checkout / "src/nested").mkdir(parents=True)
            (checkout / "src/nested/index.ts").write_bytes(name.encode())
            (checkout / "docs").mkdir()
            (checkout / "docs/guide.txt").write_bytes(b"subagents guide")
            (checkout / ".gitignore").write_bytes(b"ignored\n")
            self.assertEqual(args[-2], f"https://github.com/example/{name}.git")
            return ""
        if args == ("git", "rev-parse", "HEAD"):
            assert cwd is not None
            self.assertTrue(cwd.is_dir())
            return ("b" if cwd.name.startswith(self.names[0]) else "c") * 40
        self.fail(f"unexpected command: {args!r}")

    def test_update_replaces_all_inventories_and_preserves_unowned_metadata(self):
        data = self.manifest_data()
        with patch.object(vendor, "command", side_effect=self.staged_command), redirect_stdout(io.StringIO()) as output:
            vendor.update(data, {"pi-subagents": "Reviewed"})
        self.assertEqual(self.clones, list(self.names))
        self.assertEqual(self.references, ["Reviewed", "main"])
        self.assertEqual(data.raw, self.raw)
        published = json.loads(self.manifest.read_text())
        self.assertEqual(published["opaque"], self.raw["opaque"])
        self.assertEqual(self.manifest.read_text(), json.dumps(published, indent=2) + "\n")
        for index, name in enumerate(self.names):
            with self.subTest(name=name):
                updated = published["sources"][name]
                self.assertEqual(updated["sha"], ("b" if index == 0 else "c") * 40)
                self.assertEqual(updated["version"], "2.0.0")
                self.assertEqual(updated["ref"], self.references[index])
                expected = {
                    "package.json": vendor.git_blob_sha(b'{"version":"2.0.0"}\n'),
                    "src/nested/index.ts": vendor.git_blob_sha(name.encode()),
                }
                if name == "pi-subagents":
                    expected["docs/guide.txt"] = vendor.git_blob_sha(b"subagents guide")
                self.assertEqual(updated["files"], expected)
                self.assertFalse((self.root / updated["path"] / ".gitignore").exists())
        last = output.getvalue().splitlines()[-1]
        self.assertTrue(last.startswith("Source snapshots refreshed."))
        self.assertTrue(last.endswith("before integration."))
        self.assertEqual(sorted(path.name for path in (self.root / "sources").iterdir()), sorted((*self.names, "upstreams.json")))

    def test_update_refuses_uncommitted_sources_before_any_clone(self):
        with (
            patch.object(vendor, "command", return_value=" M sources/pi-subagents/package.json") as command,
            self.assertRaisesRegex(ValueError, "^sources has uncommitted changes; refusing to overwrite them$"),
        ):
            vendor.update(self.manifest_data(), {})
        command.assert_called_once_with("git", "status", "--porcelain", "--", "sources", cwd=self.root)
        self.assertEqual(self.snapshot(), self.original)

    def test_update_preserves_every_snapshot_if_the_second_checkout_fails(self):
        def fail_second(*args, cwd=None):
            if args[:2] == ("git", "clone") and args[-1].endswith("agent-intercom-core-checkout"):
                raise ValueError("fixture clone failed")
            return self.staged_command(*args, cwd=cwd)

        with (
            patch.object(vendor, "command", side_effect=fail_second),
            self.assertRaisesRegex(ValueError, "^fixture clone failed$"),
        ):
            vendor.update(self.manifest_data(), {})
        self.assertEqual(self.clones, ["pi-subagents"])
        self.assertEqual(self.snapshot(), self.original)

    def test_update_restores_snapshots_if_a_rename_or_manifest_commit_fails(self):
        replace = os.replace
        for failed in ("agent-intercom-core-new", "upstreams.json.tmp"):
            def fail_selected(source, destination, *, failed_name=failed):
                if Path(source).name == failed_name:
                    raise OSError(f"fixture replace failed: {failed_name}")
                return replace(source, destination)

            with (
                self.subTest(source=failed),
                patch.object(vendor, "command", side_effect=self.staged_command),
                patch.object(vendor.os, "replace", side_effect=fail_selected),
                self.assertRaisesRegex(OSError, "fixture replace failed:"),
            ):
                vendor.update(self.manifest_data(), {})
                self.assertEqual(self.snapshot(), self.original)

    def test_update_rolls_back_when_the_installed_bytes_fail_verification(self):
        replace = os.replace

        def change_after_install(source, destination):
            replace(source, destination)
            if Path(source).name == "agent-intercom-core-new":
                (Path(destination) / "src/nested/index.ts").write_bytes(b"invalid installed bytes")

        with (
            patch.object(vendor, "command", side_effect=self.staged_command),
            patch.object(vendor.os, "replace", side_effect=change_after_install),
            self.assertRaisesRegex(ValueError, r"changed=\['src/nested/index\.ts'\]"),
        ):
            vendor.update(self.manifest_data(), {})
        self.assertEqual(self.snapshot(), self.original)


    def test_update_rolls_back_if_verification_is_interrupted(self):
        with (
            patch.object(vendor, "command", side_effect=self.staged_command),
            patch.object(vendor, "check", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            vendor.update(self.manifest_data(), {})
        self.assertEqual(self.snapshot(), self.original)

    def test_update_rolls_back_if_the_first_backup_move_is_interrupted(self):
        replace = os.replace

        def interrupt_after_backup(source, destination):
            replace(source, destination)
            if Path(destination).name == "pi-subagents-previous":
                raise KeyboardInterrupt

        with (
            patch.object(vendor, "command", side_effect=self.staged_command),
            patch.object(vendor.os, "replace", side_effect=interrupt_after_backup),
            self.assertRaises(KeyboardInterrupt),
        ):
            vendor.update(self.manifest_data(), {})
        self.assertEqual(self.snapshot(), self.original)

    def test_update_preserves_the_new_snapshot_if_the_manifest_commit_is_interrupted(self):
        replace = os.replace

        def interrupt_after_commit(source, destination):
            replace(source, destination)
            if Path(destination) == self.manifest:
                raise KeyboardInterrupt

        with (
            patch.object(vendor, "command", side_effect=self.staged_command),
            patch.object(vendor.os, "replace", side_effect=interrupt_after_commit),
            self.assertRaises(KeyboardInterrupt),
        ):
            vendor.update(self.manifest_data(), {})
        with redirect_stdout(io.StringIO()):
            vendor.check(self.manifest_data().raw, self.root)
        self.assertEqual(self.manifest_data().sources["pi-subagents"].sha, "b" * 40)

    def test_update_preserves_original_backups_if_rollback_itself_fails(self):
        replace = os.replace

        def fail_restore(source, destination):
            if Path(source).name == "agent-intercom-core-previous":
                raise OSError("fixture cannot restore the original Intercom snapshot")
            return replace(source, destination)

        with (
            patch.object(vendor, "command", side_effect=self.staged_command),
            patch.object(vendor.os, "replace", side_effect=fail_restore),
            patch.object(vendor, "check", side_effect=ValueError("fixture installed verification failed")),
            self.assertRaisesRegex(OSError, "fixture cannot restore"),
        ):
            vendor.update(self.manifest_data(), {})
        self.assertEqual(self.manifest.read_bytes(), self.original["upstreams.json"])
        for name in self.names:
            backups = list((self.root / "sources").glob(f".pi-backup-*/{name}-previous/package.json"))
            self.assertEqual(len(backups), 1, name)
            self.assertEqual(backups[0].read_bytes(), self.original[f"{name}/package.json"])


    def test_update_validates_ref_before_starting_a_checkout(self):
        for ref in ("with spaces", "-leading", "two..dots"):
            with self.subTest(ref=ref):
                with (
                    patch.object(vendor, "command", return_value="") as command,
                    self.assertRaises(ValueError) as raised,
                ):
                    vendor.update(self.manifest_data(), {"pi-subagents": ref})
                self.assertEqual(str(raised.exception), f"unsafe ref: {ref}")
                command.assert_called_once_with("git", "status", "--porcelain", "--", "sources", cwd=self.root)
                self.assertEqual(self.snapshot(), self.original)

    def test_update_requires_a_resolved_revision_and_nonempty_source(self):
        for fault, message in (("revision", "invalid upstream revision for pi-subagents"),
                               ("inventory", "no source files for pi-subagents")):
            def no_input(*args: str, cwd: Path | None = None, mode: str = fault) -> str:
                if mode == "revision" and args == ("git", "rev-parse", "HEAD"):
                    return "unresolved"
                if mode == "inventory" and args[:2] == ("git", "clone"):
                    Path(args[-1]).mkdir()
                    return ""
                return self.staged_command(*args, cwd=cwd)

            with self.subTest(fault=fault):
                with patch.object(vendor, "command", side_effect=no_input), self.assertRaises(ValueError) as raised:
                    vendor.update(self.manifest_data(), {})
                self.assertEqual(str(raised.exception), message)
                self.assertEqual(self.snapshot(), self.original)
