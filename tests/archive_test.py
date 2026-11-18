import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.archive import archive, unpack, validate_members, verify


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
            (package / "alias.js").symlink_to("index.js")
            for profile in ("full", "headless-usr"):
                output = root / f"{profile}.tar.xz"
                with patch("tools.archive.shutil.copytree", wraps=shutil.copytree) as copytree:
                    manifest = archive(root / "input", output, f"pi-{profile}", "1.5.0", "aarch64-apple-darwin", profile, "a" * 40)
                self.assertEqual(manifest["profile"], profile)
                if profile == "headless-usr":
                    staging_tree = copytree.call_args_list[0].args[1]
                    self.assertEqual(staging_tree.parent.parent, root)
                    self.assertFalse(staging_tree.parent.exists())
                expected = {name: content for name, content in files.items()
                            if profile == "full" or not name.endswith((".map", ".d.ts", ".d.mts", ".d.cts"))}
                with tarfile.open(output) as bundle:
                    alias = bundle.getmember("node_modules/@scope/example/alias.js")
                    self.assertTrue(alias.issym())
                    self.assertEqual(alias.linkname, "index.js")
                    actual = {}
                    for member in bundle:
                        if member.isfile():
                            stream = bundle.extractfile(member)
                            assert stream is not None
                            actual[member.name.removeprefix("node_modules/@scope/example/")] = stream.read().decode()
                self.assertEqual(actual, expected)
                self.assertEqual(manifest["packages"], {"@scope/example": sum(len(value) for value in expected.values())})

    def test_archive_rejects_unknown_profile_before_creating_output(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            output = root / "dist/asset.tar.xz"
            with self.assertRaisesRegex(ValueError, "^unsupported profile: alternate$"):
                archive(root / "source", output, "pi", "1.5.0", "aarch64-apple-darwin", "alternate", "a" * 40)
            self.assertFalse(output.parent.exists())

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

    def test_unpack_preserves_inventory_and_validates_before_filter_handoff(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            source = root / "fixture.tar.xz"
            destination = root / "output"
            names = ["node_modules", "node_modules/example", "node_modules/example/main.js",
                     "node_modules/example/alias.js", "node_modules/example/chain.js"]
            with tarfile.open(source, "w:xz") as bundle:
                for name in names:
                    member = tarfile.TarInfo(name)
                    member.uid = member.gid = member.mtime = 0
                    member.uname = member.gname = ""
                    member.mode = 0o755 if name in names[:2] else 0o644
                    if name in names[:2]:
                        member.type = tarfile.DIRTYPE
                    elif name.endswith("main.js"):
                        member.size = 7
                    else:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "main.js" if name.endswith("alias.js") else "alias.js"
                    bundle.addfile(member, io.BytesIO(b"content") if member.size else None)
            original = tarfile.TarFile.extractall
            handoffs = []

            def extract_and_record(bundle, path, members):
                handoffs.append((path, [member.name for member in members]))
                return original(bundle, path, members=members)

            with patch.object(tarfile.TarFile, "extractall", extract_and_record):
                unpack(source, destination)
            self.assertEqual(handoffs, [(destination, names)])
            self.assertEqual((destination / names[2]).read_bytes(), b"content")
            self.assertEqual((destination / names[3]).readlink(), Path("main.js"))
            self.assertEqual((destination / names[4]).readlink(), Path("alias.js"))
            self.assertEqual(sorted(str(path.relative_to(destination)) for path in destination.rglob("*")), sorted(names))

            with tarfile.open(source, "w:xz") as bundle:
                for _ in range(2):
                    bundle.addfile(tarfile.TarInfo("node_modules/example"))
            with patch.object(tarfile.TarFile, "extractall") as extract:
                with self.assertRaisesRegex(ValueError, "duplicate archive member"):
                    unpack(source, root / "rejected")
                extract.assert_not_called()

    def test_member_inventory_rejects_conflicts_and_accepts_resolved_links(self):
        valid = [tarfile.TarInfo("node_modules/example/file"),
                 self.symlink("node_modules/example/alias", "file"),
                 self.symlink("node_modules/example/chain", "alias")]
        self.assertIsNone(validate_members(valid))
        directory = tarfile.TarInfo("node_modules/example/folder")
        directory.type = tarfile.DIRTYPE
        self.assertIsNone(validate_members([directory]))
        special = tarfile.TarInfo("node_modules/example/special")
        special.type = tarfile.FIFOTYPE
        cases = [
            ("duplicate archive member: node_modules/example/file", [valid[0], valid[0]]),
            ("unsafe archive member: node_modules/example/special", [special]),
            ("unsafe archive member: ", [tarfile.TarInfo("")]),
            ("unsafe archive member: docs/README", [tarfile.TarInfo("docs/README")]),
            ("unsafe archive member: node_modules/docs/../README", [tarfile.TarInfo("node_modules/docs/../README")]),
            ("archive member traverses symlink parent: node_modules/example/link/second/child", [
                self.symlink("node_modules/example/link", "file"), valid[0],
                tarfile.TarInfo("node_modules/example/link/second/child"),
            ]),
            ("dangling archive link: node_modules/example/alias", [self.symlink("node_modules/example/alias", "missing")]),
            ("cyclic archive link: node_modules/example/a", [
                self.symlink("node_modules/example/a", "b"), self.symlink("node_modules/example/b", "a"),
            ]),
        ]
        for message, members in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as error:
                    validate_members(members)
                self.assertEqual(str(error.exception), message)

    def test_member_validator_names_links_outside_the_member_namespace(self):
        name = "node_modules/example/alias"
        for target in ("/fixture/item", "../../..", "../../../fixture"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError) as result:
                    validate_members([self.symlink(name, target)])
                self.assertEqual(str(result.exception), f"unsafe archive link: {name}")

    def test_member_validator_reports_a_chain_leading_into_a_cycle(self):
        program = """
import tarfile
from tools.archive import validate_members

members = []
for name, target in (("a", "b"), ("b", "c"), ("c", "b")):
    item = tarfile.TarInfo(f"node_modules/example/{name}")
    item.type = tarfile.SYMTYPE
    item.linkname = target
    members.append(item)

try:
    validate_members(members)
except ValueError as error:
    print(error)
"""
        result = subprocess.run(
            [sys.executable, "-c", program], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=2,
        )
        self.assertEqual(result.stdout, "cyclic archive link: node_modules/example/a\n")
        self.assertEqual(result.stderr, "")

    def test_unpack_requires_xz_compression_before_creating_destination(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            source = root / "fixture.tar.xz"
            with tarfile.open(source, "w:gz") as bundle:
                bundle.addfile(tarfile.TarInfo("node_modules/example/README"))
            destination = root / "output"
            with self.assertRaises(tarfile.ReadError):
                unpack(source, destination)
            self.assertFalse(destination.exists())

    @staticmethod
    def symlink(name, target):
        member = tarfile.TarInfo(name)
        member.type = tarfile.SYMTYPE
        member.linkname = target
        return member


if __name__ == "__main__":
    unittest.main()
