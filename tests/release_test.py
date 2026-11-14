import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.release import TARGETS, merge, write

REVISION = "a" * 40
COMPANIONS = {
    "agent-intercom-claude": "0.10.0",
    "agent-intercom-codex": "0.10.0",
    "agent-intercom-opencode": "0.10.0",
}


def write_companions(assets: Path) -> dict:
    companions = {}
    for name, version in COMPANIONS.items():
        member = tarfile.TarInfo("package/package.json")
        payload = json.dumps({"name": name, "version": version}).encode()
        member.size = len(payload)
        member.mtime = 0
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
            bundle.addfile(member, io.BytesIO(payload))
        archive = assets / f"{name}-{version}.tgz"
        archive.write_bytes(buffer.getvalue())
        companions[name] = {
            "archive": archive.name,
            "version": version,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "bytes": archive.stat().st_size,
            "source_sha": "c" * 40,
        }
    return companions


def part(assets: Path, target: str, revision: str = REVISION, profile: str = "full") -> dict:
    archive = assets / f"pi-{profile}-1.5.0-{target}.tar.xz"
    archive.write_bytes(target.encode())
    sha256 = hashlib.sha256(target.encode()).hexdigest()
    (assets / f"pi-{profile}-1.5.0-{target}.manifest.json").write_text(json.dumps({"sha256": sha256, "source_revision": revision}))
    return {
        "schema": 1, "builder_revision": revision, "profile": profile, "product": f"pi-{profile}", "version": "1.5.0",
        "sources_sha256": "s", "components": {"c": "x"}, "companions": write_companions(assets),
        "targets": {target: {"target": target, "profile": profile, "archive": archive.name, "sha256": sha256, "bytes": len(target)}},
        "inputs": {target: {"lock_sha256": target}},
    }


class ReleaseTests(unittest.TestCase):
    def test_headless_release_retains_its_profile_identity(self):
        merged = merge(self.assets, [part(self.assets, target, profile="headless-usr") for target in TARGETS])
        self.assertEqual(merged["product"], "pi-headless-usr")
        self.assertEqual(merged["profile"], "headless-usr")
        self.assertTrue(all(record["archive"].startswith("pi-headless-usr-") for record in merged["targets"].values()))

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
        self.assertEqual([entry[1] for entry in sums], sorted(path.name for path in self.assets.iterdir() if path.name != "SHA256SUMS"))

    def test_rejects_targets_built_at_different_revisions(self):
        parts = [part(self.assets, target) for target in TARGETS[:2]] + [part(self.assets, TARGETS[2], "b" * 40)]
        with self.assertRaisesRegex(ValueError, "builder_revision differs"):
            merge(self.assets, parts)

    def test_rejects_incomplete_target_set(self):
        with self.assertRaisesRegex(ValueError, "requires targets"):
            merge(self.assets, [part(self.assets, target) for target in TARGETS[:2]])

    def test_rejects_archive_that_differs_from_its_record(self):
        parts = [part(self.assets, target) for target in TARGETS]
        (self.assets / "pi-full-1.5.0-x86_64-unknown-linux-musl.tar.xz").write_bytes(b"tampered!")
        with self.assertRaisesRegex(ValueError, "mismatch for x86_64-unknown-linux-musl"):
            merge(self.assets, parts)

    def test_rejects_manifest_that_differs_from_its_archive_record(self):
        parts = [part(self.assets, target) for target in TARGETS]
        (self.assets / "pi-full-1.5.0-aarch64-apple-darwin.manifest.json").write_text(json.dumps({"sha256": "0" * 64, "source_revision": REVISION}))
        with self.assertRaisesRegex(ValueError, "manifest differs from provenance for aarch64-apple-darwin"):
            merge(self.assets, parts)

    def test_rejects_target_record_with_extra_identity_fields(self):
        parts = [part(self.assets, target) for target in TARGETS]
        parts[0]["targets"]["aarch64-apple-darwin"]["builder_revision"] = REVISION
        with self.assertRaisesRegex(ValueError, "invalid target record"):
            merge(self.assets, parts)


if __name__ == "__main__":
    unittest.main()
