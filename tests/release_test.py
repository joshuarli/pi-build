import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.release import TARGETS, merge, write

REVISION = "a" * 40


def part(assets: Path, target: str, revision: str = REVISION) -> dict:
    archive = assets / f"{target}-full.tar.gz"
    archive.write_bytes(target.encode())
    return {
        "schema": 1, "builder_revision": revision, "profile": "full", "sources_sha256": "s", "components": {"c": "x"},
        "targets": {target: {"target": target, "profile": "full", "archive": archive.name,
                             "sha256": hashlib.sha256(target.encode()).hexdigest(), "bytes": len(target)}},
        "inputs": {target: {"lock_sha256": target}},
    }


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        Path(".work/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=".work/tmp")
        self.assets = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_merged_assets_satisfy_the_consumer_identity_checks(self):
        merged = merge(self.assets, [part(self.assets, target) for target in TARGETS])
        write(self.assets, merged)
        provenance = json.loads((self.assets / "provenance.json").read_text())
        sums = [line.split() for line in (self.assets / "SHA256SUMS").read_text().splitlines()]
        for target in TARGETS:
            record = provenance["targets"][target]
            self.assertEqual(provenance["builder_revision"], REVISION)
            self.assertEqual(set(record), {"target", "profile", "archive", "sha256", "bytes"})
            self.assertEqual([entry for entry in sums if entry[1] == record["archive"]], [[record["sha256"], record["archive"]]])

    def test_rejects_targets_built_at_different_revisions(self):
        parts = [part(self.assets, target) for target in TARGETS[:2]] + [part(self.assets, TARGETS[2], "b" * 40)]
        with self.assertRaisesRegex(ValueError, "builder_revision differs"):
            merge(self.assets, parts)

    def test_rejects_incomplete_target_set(self):
        with self.assertRaisesRegex(ValueError, "requires targets"):
            merge(self.assets, [part(self.assets, target) for target in TARGETS[:2]])

    def test_rejects_archive_that_differs_from_its_record(self):
        parts = [part(self.assets, target) for target in TARGETS]
        (self.assets / "linux-x64-full.tar.gz").write_bytes(b"tampered!")
        with self.assertRaisesRegex(ValueError, "mismatch for linux-x64"):
            merge(self.assets, parts)

    def test_rejects_target_record_with_extra_identity_fields(self):
        parts = [part(self.assets, target) for target in TARGETS]
        parts[0]["targets"]["darwin-arm64"]["builder_revision"] = REVISION
        with self.assertRaisesRegex(ValueError, "invalid target record"):
            merge(self.assets, parts)


if __name__ == "__main__":
    unittest.main()
