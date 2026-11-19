import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import sizes


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
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(sys, "argv", ["sizes.py", "full", *map(str, args)]),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            previous = Path.cwd()
            try:
                os.chdir(root)
                code = sizes.main()
            finally:
                os.chdir(previous)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_missing_archive_manifest_and_unreadable_manifest_fail(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            self.assertNotEqual(self.run_sizes(root)[0], 0)
            _, manifest, _ = self.fixture(root / "dist/full")
            manifest.unlink()
            self.assertNotEqual(self.run_sizes(root)[0], 0)
            manifest.write_text("{")
            self.assertNotEqual(self.run_sizes(root)[0], 0)
            self.fixture(root / "dist/full", target="other")
            (root / "dist/full/pi-full-1-target-a.tar.xz").unlink()
            self.assertNotEqual(self.run_sizes(root)[0], 0)

    def test_identity_and_archive_integrity_fail(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            path, manifest_path, manifest = self.fixture(root / "dist/full")
            for field, value in (("target", "other"), ("profile", "headless-usr")):
                changed = dict(manifest, **{field: value})
                manifest_path.write_text(json.dumps(changed))
                self.assertNotEqual(self.run_sizes(root)[0], 0)
            manifest_path.write_text(json.dumps(manifest))
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            self.assertNotEqual(self.run_sizes(root)[0], 0)

    def test_pairs_threshold_and_packages(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            reference = root / "reference"
            candidate = root / "dist/full"
            self.fixture(reference, packages={"pkg": 100, "removed": 10})
            _, manifest_path, manifest = self.fixture(candidate, packages={"pkg": 120, "new": 10})
            result = self.run_sizes(root, reference)
            self.assertEqual(result[0], 1, result[2])
            self.assertIn("pkg: 100 -> 120 (+20)", result[1])
            self.assertIn("new: 0 -> 10 (+10)", result[1])
            self.assertIn("compressed=", result[1])
            self.assertEqual(self.run_sizes(root, reference, "--threshold", "30")[0], 0)
            manifest["packages"] = {"pkg": 100, "removed": 10}
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root, reference)[0], 0)
            manifest["packages"] = {"pkg": 1}
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root, reference)[0], 0)
            self.fixture(reference, target="target-b")
            self.assertNotEqual(self.run_sizes(root, reference)[0], 0)
            self.fixture(candidate, target="target-c")
            self.assertNotEqual(self.run_sizes(root, reference)[0], 0)
            self.assertNotEqual(self.run_sizes(root, root / "missing")[0], 0)

    def test_compressed_growth_fails_even_when_payload_is_equal(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            reference = root / "reference"
            self.fixture(reference, data=b"a" * 4096)
            self.fixture(root / "dist/full", data=bytes(range(256)) * 16)
            result = self.run_sizes(root, reference)
            self.assertEqual(result[0], 1, result[2])
            self.assertIn("payload=100 -> 100 (+0)", result[1])

    def test_without_digest_still_verifies_size(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            _, manifest_path, manifest = self.fixture(root / "dist/full")
            del manifest["sha256"]
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root)[0], 0)
            manifest["bytes"] += 1
            manifest_path.write_text(json.dumps(manifest))
            self.assertNotEqual(self.run_sizes(root)[0], 0)

    def test_exact_reports_and_threshold_boundary(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            reference = root / "reference"
            _, _, old = self.fixture(reference, packages={"pkg": 100})
            _, manifest_path, new = self.fixture(root / "dist/full", packages={"pkg": 105, "new": 0})
            size = old["bytes"]
            self.assertEqual(self.run_sizes(root), (0, f"target-a compressed={size} payload=105\n", ""))
            report = f"target-a compressed={size} -> {size} (+0) payload=100 -> 105 (+5)\n  pkg: 100 -> 105 (+5)\n"
            self.assertEqual(self.run_sizes(root, reference), (0, report, ""))
            self.assertEqual(self.run_sizes(root, reference, "--threshold", "4"), (1, report, ""))
            new["packages"] = {"pkg": 99}
            manifest_path.write_text(json.dumps(new))
            self.assertEqual(self.run_sizes(root, reference),
                             (0, f"target-a compressed={size} -> {size} (+0) payload=100 -> 99 (-1)\n", ""))

    def test_exact_errors_and_pair_differences(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            self.assertEqual(self.run_sizes(root), (1, "", "sizes: no archives in dist/full\n"))
            path, manifest_path, manifest = self.fixture(root / "dist/full")
            manifest_path.unlink()
            self.assertEqual(self.run_sizes(root), (1, "", f"sizes: [Errno 2] No such file or directory: 'dist/full/{manifest_path.name}'\n"))
            manifest_path.write_text("{")
            self.assertEqual(self.run_sizes(root), (1, "", "sizes: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)\n"))
            manifest_path.write_text(json.dumps(manifest))
            path.unlink()
            self.fixture(root / "dist/full", target="other")
            self.assertEqual(self.run_sizes(root), (1, "", f"sizes: missing archive: dist/full/{path.name}\n"))
            path, manifest_path, manifest = self.fixture(root / "dist/full")
            manifest["archive"] = "wrong.tar.xz"
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root), (1, "", f"sizes: artifact identity mismatch: dist/full/{path.name}\n"))
            manifest["archive"] = path.name
            manifest_path.write_text(json.dumps(manifest))
            reference = root / "reference"
            self.fixture(reference, target="target-b")
            self.assertEqual(self.run_sizes(root, reference),
                             (1, "", "sizes: target pairs mismatch: reference only=['target-b'], candidate only=['other', 'target-a']\n"))

    def test_manifest_validation(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            path, manifest_path, manifest = self.fixture(root / "dist/full")
            cases = (
                ("target", "", "artifact identity mismatch", path.name),
                ("target", 1, "artifact identity mismatch", path.name),
                ("profile", "other", "artifact identity mismatch", path.name),
                ("product", "other", "artifact identity mismatch", path.name),
                ("version", "2", "artifact identity mismatch", path.name),
                ("packages", [], "invalid package sizes", manifest_path.name),
                ("packages", {"pkg": -1}, "invalid package sizes", manifest_path.name),
                ("packages", {"pkg": True}, "invalid package sizes", manifest_path.name),
                ("bytes", -1, "invalid archive size", manifest_path.name),
                ("bytes", True, "invalid archive size", manifest_path.name),
            )
            for field, value, message, name in cases:
                with self.subTest(field=field, value=value):
                    manifest_path.write_text(json.dumps(dict(manifest, **{field: value})))
                    self.assertEqual(self.run_sizes(root), (1, "", f"sizes: {message}: dist/full/{name}\n"))
            del manifest["sha256"]
            manifest["schema_version"] = 2
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root), (1, "", f"sizes: archive identity or size mismatch: dist/full/{path.name}\n"))

    def test_invalid_thresholds(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            for threshold in ("-1", "nan", "inf"):
                with self.subTest(threshold=threshold):
                    with self.assertRaises(SystemExit) as error:
                        self.run_sizes(root, "--threshold", threshold)
                    self.assertEqual(error.exception.code, 2)

    def test_digest_is_checked_and_xz_format_is_required(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            path, manifest_path, manifest = self.fixture(root / "dist/full")
            manifest["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            code, out, err = self.run_sizes(root)
            self.assertEqual((code, out), (1, ""))
            self.assertEqual(err, "sizes: archive digest or size mismatch\n")
            with tarfile.open(path, "w:gz") as bundle:
                member = tarfile.TarInfo("file")
                bundle.addfile(member)
            del manifest["sha256"]
            manifest["bytes"] = path.stat().st_size
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.run_sizes(root), (1, "", "sizes: not an lzma file\n"))

    def test_duplicate_and_empty_target_identity(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            directory = root / "dist/full"
            path, manifest_path, manifest = self.fixture(directory)
            second = directory / "pi-full-2-target-a.tar.xz"
            second.write_bytes(path.read_bytes())
            second_manifest = second.with_name(second.name.removesuffix(".tar.xz") + ".manifest.json")
            second_manifest.write_text(json.dumps(dict(manifest, version="2", archive=second.name)))
            self.assertEqual(self.run_sizes(root), (1, "", "sizes: duplicate target: target-a\n"))
            second.unlink()
            second_manifest.unlink()
            empty = directory / "pi-full-1-.tar.xz"
            path.rename(empty)
            manifest_path.unlink()
            empty_manifest = empty.with_name(empty.name.removesuffix(".tar.xz") + ".manifest.json")
            empty_manifest.write_text(json.dumps(dict(manifest, target="", archive=empty.name)))
            self.assertEqual(self.run_sizes(root), (1, "", f"sizes: artifact identity mismatch: dist/full/{empty.name}\n"))

    def test_zero_size_and_threshold_errors(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            _, manifest_path, manifest = self.fixture(root / "dist/full")
            manifest["bytes"] = 0
            manifest_path.write_text(json.dumps(manifest))
            code, out, err = self.run_sizes(root)
            self.assertEqual((code, out), (1, ""))
            self.assertNotIn("invalid archive size", err)
            stderr = io.StringIO()
            with (patch.object(sys, "argv", ["sizes.py", "full", "--threshold", "-1"]),
                  redirect_stderr(stderr), self.assertRaises(SystemExit) as error):
                sizes.main()
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(stderr.getvalue(), "usage: sizes.py [-h] [--threshold THRESHOLD] profile [reference]\nsizes.py: error: threshold must be a finite nonnegative percentage\n")

    def test_default_and_zero_threshold_and_multiple_targets(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as tmp:
            root = Path(tmp).resolve()
            reference = root / "reference"
            candidate = root / "dist/full"
            self.fixture(reference, packages={"pkg": 100})
            self.fixture(candidate, packages={"pkg": 106})
            self.assertEqual(self.run_sizes(root, reference)[0], 1)
            self.assertEqual(self.run_sizes(root, reference, "--threshold", "0")[0], 1)
            self.fixture(reference, target="target-b")
            self.fixture(candidate, target="target-b")
            self.assertEqual(self.run_sizes(root, reference)[0], 1)
