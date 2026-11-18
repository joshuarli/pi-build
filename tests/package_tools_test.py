import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(ROOT))
from tools import fetch


class PackageToolsTests(unittest.TestCase):
    def test_fetch_reuses_verified_inputs_in_requested_order(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            destination = root / "cache"
            destination.mkdir()
            lock = root / "sources.lock.json"
            entries = []
            cached = {}
            for name, contents in (("first", b"fixture one"), ("second", b"fixture two")):
                cached[name] = destination / f"{name}.datX"
                cached[name].write_bytes(contents)
                entries.append({
                    "name": name, "version": "1", "size": len(contents),
                    "sha256": hashlib.sha256(contents).hexdigest(),
                    "url": f"https://example.invalid/pin/{cached[name].name}/",
                })
            lock.write_text(json.dumps({"schema_version": 1, "inputs": entries}))
            args = ["fetch.py", str(lock), str(destination), "second", "first"]
            before = {name: (path.read_bytes(), path.stat().st_mtime_ns) for name, path in cached.items()}
            with (
                patch.object(sys, "argv", args),
                patch("urllib.request.urlopen", side_effect=AssertionError("network access")),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(fetch.main(), 0)
            self.assertEqual(stdout.getvalue().splitlines(), [str(cached["second"]), str(cached["first"])])
            self.assertEqual({name: (path.read_bytes(), path.stat().st_mtime_ns) for name, path in cached.items()}, before)

            cached["first"].write_bytes(b"corrupt")
            with (
                patch.object(sys, "argv", args[:3] + ["first"]),
                patch("urllib.request.urlopen", return_value=io.BytesIO(before["first"][0])) as download,
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(fetch.main(), 0)
            self.assertEqual(download.call_count, 1)
            self.assertEqual(cached["first"].read_bytes(), before["first"][0])
            self.assertEqual(stdout.getvalue(), f"{cached['first']}\n")

    def test_fetch_with_no_names_creates_the_requested_cache(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            destination = root / "new/cache"
            lock = root / "sources.lock.json"
            lock.write_text(json.dumps({"schema_version": 1, "inputs": []}))
            with (
                patch.object(sys, "argv", ["fetch.py", str(lock), str(destination)]),
                patch("urllib.request.urlopen", side_effect=AssertionError("network access")),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(fetch.main(), 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertTrue(destination.is_dir())
            self.assertEqual(list(destination.iterdir()), [])

    def test_fetch_requires_a_lock_and_destination(self):
        with patch.object(sys, "argv", ["fetch.py", "unused.lock"]), redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(fetch.main(), 2)
        self.assertIn("Usage: python tools/fetch.py SOURCES_LOCK DOWNLOAD_DIR", stderr.getvalue())

        result = subprocess.run(
            [sys.executable, "-I", TOOLS / "fetch.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Usage: python tools/fetch.py SOURCES_LOCK DOWNLOAD_DIR", result.stderr)

    def test_pack_normalizes_metadata_and_order_without_changing_contents(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            payload = b"export default 1\n"
            specs = (
                ("pkg/file.js", tarfile.REGTYPE, 0o644, ""),
                ("pkg", tarfile.DIRTYPE, 0o755, ""),
                ("pkg/alias.js", tarfile.SYMTYPE, 0o777, "file.js"),
            )
            outputs = []
            for index, members in enumerate((specs, specs[::-1]), start=1):
                source = root / f"input-{index}.tgz"
                output = root / f"output-{index}.tgz"
                with tarfile.open(source, "w:gz") as archive:
                    for name, kind, mode, target in members:
                        member = tarfile.TarInfo(name)
                        member.type = kind
                        member.mode = mode
                        member.linkname = target
                        member.uid = member.gid = 100 + index
                        member.uname = member.gname = f"builder-{index}"
                        member.mtime = 1000 + index
                        stream = io.BytesIO(payload) if member.isfile() else None
                        member.size = len(payload) if stream is not None else 0
                        archive.addfile(member, stream)
                subprocess.run([sys.executable, "-I", TOOLS / "pack.py", source, output], check=True)
                outputs.append(output)

            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            with tarfile.open(outputs[0], "r:gz") as archive:
                self.assertEqual(
                    [(m.name, m.type, m.mode, m.linkname) for m in archive.getmembers()],
                    sorted(specs),
                )
                for member in archive.getmembers():
                    self.assertEqual((member.uid, member.gid, member.uname, member.gname, member.mtime), (0, 0, "", "", 0))
                stream = archive.extractfile("pkg/file.js")
                assert stream is not None
                self.assertEqual(stream.read(), payload)

    def test_sizes_lists_only_the_selected_profile_with_payload_totals(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            fixtures = (
                ("full", "z", "aarch64-apple-darwin", 52, {"pi": 9}),
                ("full", "a", "x86_64-unknown-linux-musl", 300, {"pi": 11, "runtime": 23}),
                ("headless-usr", "b", "aarch64-apple-darwin", 100, {"pi": 80}),
            )
            for profile, name, target, compressed, packages in fixtures:
                destination = root / "dist" / profile
                destination.mkdir(parents=True, exist_ok=True)
                (destination / f"{name}.tar.xz").touch()
                (destination / f"{name}.manifest.json").write_text(
                    json.dumps({"target": target, "bytes": compressed, "packages": packages}),
                    encoding="utf-8",
                )
            result = subprocess.run(
                [sys.executable, "-I", TOOLS / "sizes.py", "full"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.stdout.splitlines(), [
                "x86_64-unknown-linux-musl compressed=300 payload=34",
                "aarch64-apple-darwin compressed=52 payload=9",
            ])
