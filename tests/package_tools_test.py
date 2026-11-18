import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"


class PackageToolsTests(unittest.TestCase):
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
