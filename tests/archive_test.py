import json
import tempfile
import unittest
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.archive import archive, validate_members, verify


class ArchiveTests(unittest.TestCase):
    def test_same_tree_has_same_archive_and_manifest_identity(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            package = root / "input/node_modules/example"
            package.mkdir(parents=True)
            (package / "index.js").write_text("export default 1\n")
            first = archive(root / "input", root / "first.tar.gz", "darwin-arm64", "full", "abc123")
            second = archive(root / "input", root / "second.tar.gz", "darwin-arm64", "full", "abc123")
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["packages"], {"example": len("export default 1\n")})
            self.assertEqual(verify(root / "first.tar.gz", root / "first.tar.gz.manifest.json", "darwin-arm64", "full")["sha256"], first["sha256"])
            manifest = json.loads((root / "first.tar.gz.manifest.json").read_text())
            manifest["target"] = "linux-x64"
            (root / "bad.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "identity"):
                verify(root / "first.tar.gz", root / "bad.json", "darwin-arm64", "full")

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
