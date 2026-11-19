import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools/sizes.py"


class SizesTests(unittest.TestCase):
    def fixture(self, directory, target="target-a", profile="full", packages=None, data=b"fixture"):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"pi-{profile}-1-{target}.tar.xz"
        with tarfile.open(path, "w:xz") as bundle:
            member = tarfile.TarInfo("node_modules/pkg/file")
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
        manifest = {
            "schema_version": 1, "target": target, "profile": profile,
            "product": f"pi-{profile}", "version": "1", "archive": path.name,
            "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "packages": packages if packages is not None else {"pkg": 100},
        }
        manifest_path = path.with_name(path.name.removesuffix(".tar.xz") + ".manifest.json")
        manifest_path.write_text(json.dumps(manifest))
        return path, manifest_path, manifest

    def run_sizes(self, root, *args):
        return subprocess.run([sys.executable, "-I", SCRIPT, "full", *map(str, args)], cwd=root,
                              capture_output=True, text=True, check=False)

    def test_missing_archive_manifest_and_unreadable_manifest_fail(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            self.assertNotEqual(self.run_sizes(root).returncode, 0)
            _, manifest, _ = self.fixture(root / "dist/full")
            manifest.unlink()
            self.assertNotEqual(self.run_sizes(root).returncode, 0)
            manifest.write_text("{")
            self.assertNotEqual(self.run_sizes(root).returncode, 0)
            self.fixture(root / "dist/full", target="other")
            (root / "dist/full/pi-full-1-target-a.tar.xz").unlink()
            self.assertNotEqual(self.run_sizes(root).returncode, 0)

    def test_identity_and_archive_integrity_fail(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            path, manifest_path, manifest = self.fixture(root / "dist/full")
            for field, value in (("target", "other"), ("profile", "headless-usr")):
                changed = dict(manifest, **{field: value})
                manifest_path.write_text(json.dumps(changed))
                self.assertNotEqual(self.run_sizes(root).returncode, 0)
            manifest_path.write_text(json.dumps(manifest))
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            self.assertNotEqual(self.run_sizes(root).returncode, 0)

    def test_pairs_threshold_and_packages(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            reference = root / "reference"
            candidate = root / "dist/full"
            self.fixture(reference, packages={"pkg": 100, "removed": 10})
            _, manifest_path, manifest = self.fixture(candidate, packages={"pkg": 120, "new": 10})
            result = self.run_sizes(root, reference)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("pkg: 100 -> 120 (+20)", result.stdout)
            self.assertIn("new: 0 -> 10 (+10)", result.stdout)
            self.assertIn("compressed=", result.stdout)
            self.assertEqual(self.run_sizes(root, reference, "--threshold", "30").returncode, 0)
            manifest["packages"] = {"pkg": 100, "removed": 10}
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root, reference).returncode, 0)
            manifest["packages"] = {"pkg": 1}
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root, reference).returncode, 0)
            self.fixture(reference, target="target-b")
            self.assertNotEqual(self.run_sizes(root, reference).returncode, 0)
            self.fixture(candidate, target="target-c")
            self.assertNotEqual(self.run_sizes(root, reference).returncode, 0)
            self.assertNotEqual(self.run_sizes(root, root / "missing").returncode, 0)

    def test_compressed_growth_fails_even_when_payload_is_equal(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            reference = root / "reference"
            self.fixture(reference, data=b"a" * 4096)
            self.fixture(root / "dist/full", data=bytes(range(256)) * 16)
            result = self.run_sizes(root, reference)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("payload=100 -> 100 (+0)", result.stdout)

    def test_without_digest_still_verifies_size(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            _, manifest_path, manifest = self.fixture(root / "dist/full")
            del manifest["sha256"]
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root).returncode, 0)
            manifest["bytes"] += 1
            manifest_path.write_text(json.dumps(manifest))
            self.assertNotEqual(self.run_sizes(root).returncode, 0)
