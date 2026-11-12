import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.vendor import check, git_blob_sha, materialize


class VendorTests(unittest.TestCase):
    def test_materialization_rejects_changed_snapshot_and_copies_only_manifest_files(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            source = root / "sources/pi-subagents"
            source.mkdir(parents=True)
            content = b"export const approved = true;\n"
            (source / "index.ts").write_bytes(content)
            (source / ".npmignore").write_text("unlisted packaging rules\n")
            data = {"sources": {"pi-subagents": {
                "path": "sources/pi-subagents",
                "sha": "0" * 40,
                "files": {"index.ts": git_blob_sha(content)},
            }}}
            output = root / "build/packages"
            materialize(data, output, root)
            self.assertEqual((output / "pi-subagents/index.ts").read_bytes(), content)
            self.assertFalse((output / "pi-subagents/.npmignore").exists())
            (source / "index.ts").write_text("changed after import\n")
            with self.assertRaisesRegex(ValueError, "changed"):
                check(data, root)


if __name__ == "__main__":
    unittest.main()
