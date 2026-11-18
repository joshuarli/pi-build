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
            checkout = Path(args[-1])
            self.assertEqual(checkout.parent.parent, self.root / "sources")
            name = checkout.name.removesuffix("-checkout")
            self.clones.append(name)
            self.references.append(args[args.index("--branch") + 1])
            checkout.mkdir()
            (checkout / "package.json").write_bytes(b'{"version":"2.0.0"}\n')
            (checkout / "src").mkdir()
            (checkout / "src/index.ts").write_bytes(name.encode())
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
            vendor.update(data, {"pi-subagents": "reviewed"})
        self.assertEqual(self.clones, list(self.names))
        self.assertEqual(self.references, ["reviewed", "main"])
        self.assertEqual(data.raw, self.raw)
        published = json.loads(self.manifest.read_text())
        self.assertEqual(published["opaque"], self.raw["opaque"])
        for index, name in enumerate(self.names):
            with self.subTest(name=name):
                updated = published["sources"][name]
                self.assertEqual(updated["sha"], ("b" if index == 0 else "c") * 40)
                self.assertEqual(updated["version"], "2.0.0")
                self.assertEqual(updated["ref"], self.references[index])
                self.assertEqual(updated["files"], {
                    "package.json": vendor.git_blob_sha(b'{"version":"2.0.0"}\n'),
                    "src/index.ts": vendor.git_blob_sha(name.encode()),
                })
                self.assertFalse((self.root / updated["path"] / ".gitignore").exists())
        self.assertIn("Source snapshots refreshed.", output.getvalue())
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
                (Path(destination) / "src/index.ts").write_bytes(b"invalid installed bytes")

        with (
            patch.object(vendor, "command", side_effect=self.staged_command),
            patch.object(vendor.os, "replace", side_effect=change_after_install),
            self.assertRaisesRegex(ValueError, r"changed=\['src/index\.ts'\]"),
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
