import hashlib
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.archive import archive, validate_members, verify


class ArchiveTests(unittest.TestCase):
    def test_headless_filters_types_and_maps_but_preserves_documentation(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            package = root / "input/node_modules/@scope/example"
            package.mkdir(parents=True)
            files = {"index.js": "export default 1\n", "README.md": "read me", "LICENSE": "license",
                     "docs/guide.md": "guide", "examples/extension.ts": "export default 1",
                     "index.js.map": "map", "index.d.ts": "types", "index.d.mts": "types", "index.d.cts": "types"}
            for name, content in files.items():
                path = package / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            for profile in ("full", "headless-usr"):
                output = root / f"{profile}.tar.xz"
                manifest = archive(root / "input", output, f"pi-{profile}", "1.5.0", "aarch64-apple-darwin", profile, "a" * 40)
                expected = {name: content for name, content in files.items()
                            if profile == "full" or not name.endswith((".map", ".d.ts", ".d.mts", ".d.cts"))}
                with tarfile.open(output) as bundle:
                    actual = {}
                    for member in bundle:
                        if member.isfile():
                            stream = bundle.extractfile(member)
                            assert stream is not None
                            actual[member.name.removeprefix("node_modules/@scope/example/")] = stream.read().decode()
                self.assertEqual(actual, expected)
                self.assertEqual(manifest["packages"], {"@scope/example": sum(len(value) for value in expected.values())})

    def test_same_tree_has_same_archive_and_manifest_identity(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            package = root / "input/node_modules/example"
            package.mkdir(parents=True)
            (package / "index.js").write_text("export default 1\n")
            first = archive(root / "input", root / "first.tar.xz", "pi-full", "1.5.0", "aarch64-apple-darwin", "full", "a" * 40)
            second = archive(root / "input", root / "second.tar.xz", "pi-full", "1.5.0", "aarch64-apple-darwin", "full", "a" * 40)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["packages"], {"example": len("export default 1\n")})
            manifest_file = root / "pi-full-1.5.0-aarch64-apple-darwin.manifest.json"
            self.assertEqual(manifest_file.is_file(), True)
            self.assertEqual(verify(root / "first.tar.xz", manifest_file, "aarch64-apple-darwin", "full")["sha256"], first["sha256"])
            manifest = json.loads(manifest_file.read_text())
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual((manifest["product"], manifest["version"], manifest["source_revision"]), ("pi-full", "1.5.0", "a" * 40))
            self.assertEqual(manifest["sources_lock_sha256"], hashlib.sha256(Path("sources.lock.json").read_bytes()).hexdigest())
            manifest["target"] = "x86_64-unknown-linux-musl"
            (root / "bad.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "^artifact identity mismatch$"):
                verify(root / "first.tar.xz", root / "bad.json", "aarch64-apple-darwin", "full")

    def test_real_asset_record_inventory_and_verification(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            modules = root / "input/node_modules"
            package = modules / "@scope/example"
            package.mkdir(parents=True)
            (package / "index.js").write_bytes(b"abc")
            (package / "extra.js").write_bytes(b"12345")
            other = modules / "other"
            other.mkdir()
            (other / "main.js").write_bytes(b"hello!")
            (other / "alias.js").symlink_to("main.js")
            output = root / "nested/output/asset.tar.xz"
            manifest = archive(root / "input", output, "pi-full", "1.5.0", "aarch64-apple-darwin", "full", "a" * 40)
            manifest_file = output.parent / "pi-full-1.5.0-aarch64-apple-darwin.manifest.json"
            self.assertEqual(json.loads(manifest_file.read_text()), manifest)
            self.assertEqual(manifest["archive"], "asset.tar.xz")
            self.assertEqual(manifest["bytes"], len(output.read_bytes()))
            self.assertEqual(manifest["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(manifest["source_manifest_sha256"], hashlib.sha256(Path("sources/upstreams.json").read_bytes()).hexdigest())
            self.assertEqual(manifest["packages"], {"@scope/example": 8, "other": 6})
            with tarfile.open(output, "r:xz") as bundle:
                self.assertTrue(all(member.mtime == 0 for member in bundle.getmembers()))
            self.assertEqual(verify(output, manifest_file, "aarch64-apple-darwin", "full"), manifest)
            for field, value in (("bytes", manifest["bytes"] + 1), ("sha256", "0" * 64)):
                with self.subTest(field=field):
                    invalid = {**manifest, field: value}
                    manifest_file.write_text(json.dumps(invalid))
                    with self.assertRaisesRegex(ValueError, "^archive digest or size mismatch$"):
                        verify(output, manifest_file, "aarch64-apple-darwin", "full")
            gzip_path = root / "asset.tar.gz"
            with tarfile.open(output, "r:xz") as source, tarfile.open(gzip_path, "w:gz") as compressed:
                for member in source:
                    compressed.addfile(member, source.extractfile(member) if member.isfile() else None)
            invalid = {**manifest, "bytes": gzip_path.stat().st_size, "sha256": hashlib.sha256(gzip_path.read_bytes()).hexdigest()}
            manifest_file.write_text(json.dumps(invalid))
            with self.assertRaises(tarfile.ReadError):
                verify(gzip_path, manifest_file, "aarch64-apple-darwin", "full")

    def test_archive_paths_reject_symlink_parent_and_dangling_chain(self):
        with self.assertRaisesRegex(ValueError, "symlink parent"):
            validate_members([
                self.symlink("node_modules/link", "target"),
                tarfile.TarInfo("node_modules/target"),
                tarfile.TarInfo("node_modules/link/file"),
            ])
        with self.assertRaisesRegex(ValueError, "dangling"):
            validate_members([self.symlink("node_modules/a", "b")])

    @staticmethod
    def symlink(name, target):
        member = tarfile.TarInfo(name)
        member.type = tarfile.SYMTYPE
        member.linkname = target
        return member


if __name__ == "__main__":
    unittest.main()
