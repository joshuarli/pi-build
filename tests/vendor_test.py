import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import vendor
from tools.vendor import check, git_blob_sha, materialize, parse_sources, source_files


class VendorTests(unittest.TestCase):
    def test_source_inventory_uses_the_snapshot_family_and_exclusions(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            files = (
                "z/tool.cjs", "package.json", "src/index.ts", "agents/main.md",
                "docs/guide.txt", "broker/config.json", "assets/logo.txt",
                ".github/workflows/ci.yml", "src/main.test.ts", "dist/bundle.cjs",
                "package-lock.json", "src/logo.webp", ".gitignore",
            )
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            shared = ["package.json", "src/index.ts", "z/tool.cjs"]
            cases = {
                "pi-subagents": sorted([*shared, "agents/main.md", "docs/guide.txt"]),
                "agent-intercom-core": sorted([*shared, "broker/config.json"]),
                "agent-intercom-claude": sorted(files[:7]),
                "agent-intercom-codex": sorted(files[:7]),
                "agent-intercom-opencode": sorted(files[:7]),
            }
            for name, expected in cases.items():
                with self.subTest(snapshot=name):
                    self.assertEqual([path.relative_to(root).as_posix() for path in source_files(root, name)], expected)
            alias = root / "src/alias.ts"
            alias.symlink_to("index.ts")
            with self.assertRaises(ValueError) as raised:
                source_files(root, "pi-subagents")
            self.assertEqual(str(raised.exception), f"symlink in upstream snapshot: {alias}")

    def test_git_blob_hash_uses_bytes_and_git_header(self):
        self.assertEqual(git_blob_sha(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertEqual(git_blob_sha(b"abc\n"), "8baef1b4abc478178b004d62031cf7fe6db6f903")
        self.assertEqual(git_blob_sha(bytes([0, 255]) + b"pi"), "f91b2fcc2d9c4f697e2a1329818e73602f70b47a")

    def test_load_checks_pinned_manifest_identity_and_inventory(self):
        tracked = json.loads((ROOT / "sources/upstreams.json").read_text())
        name = "pi-subagents"
        source = tracked["sources"][name]
        paths = {
            "pi-subagents", "agent-intercom-pi", "agent-intercom-core", "pi-muse-subscription",
            "agent-intercom-claude", "agent-intercom-codex", "agent-intercom-opencode", "pi-devin-local",
        }
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            manifest = Path(directory) / "upstreams.json"
            with patch.object(vendor, "MANIFEST", manifest):
                manifest.write_text(json.dumps(tracked))
                loaded = vendor.load()
                self.assertEqual(loaded.raw, tracked)
                self.assertEqual(set(loaded.sources), paths)
                self.assertEqual(loaded.sources[name].files, source["files"])
                self.assertEqual(loaded.sources[name].sha, source["sha"])
                mixed_case = {**source, "repository": "ExampleOwner/ExampleRepo"}
                manifest.write_text(json.dumps({
                    **tracked, "sources": {**tracked["sources"], name: mixed_case},
                }))
                self.assertEqual(vendor.load().sources[name].raw["repository"], "ExampleOwner/ExampleRepo")

                cases = [
                    ({**tracked, "schema": 2}, "unsupported or incomplete Pi vendor manifest"),
                    ({**tracked, "sources": {}}, "unsupported or incomplete Pi vendor manifest"),
                ]
                for field, value, message in (
                    ("path", "sources/other", f"invalid identity for {name}"),
                    ("sha", "invalid", f"invalid identity for {name}"),
                    ("repository", 7, f"invalid upstream repository for {name}"),
                    ("repository", "missing-owner", f"invalid upstream repository for {name}"),
                    ("files", {}, f"empty source inventory for {name}"),
                    ("files", {"index.ts": "invalid"}, f"invalid upstream file hashes for {name}"),
                ):
                    cases.append(({**tracked, "sources": {
                        **tracked["sources"], name: {**source, field: value},
                    }}, message))
                for raw, message in cases:
                    with self.subTest(message=message):
                        manifest.write_text(json.dumps(raw))
                        with self.assertRaises(ValueError) as raised:
                            vendor.load()
                        self.assertEqual(str(raised.exception), message)

    def test_parse_preserves_opaque_manifest_fields(self):
        data = {"sources": {"example": {
            "path": "sources/example", "sha": "revision", "files": {"index.ts": "hash"},
            "extra": {"nested": [1, None, {"flag": True}]},
        }}, "metadata": ["preserved"]}
        before = json.dumps(data, indent=2)
        sources = parse_sources(data)
        self.assertEqual(sources["example"].path, "sources/example")
        self.assertEqual(sources["example"].sha, "revision")
        self.assertEqual(sources["example"].files, {"index.ts": "hash"})
        self.assertIs(sources["example"].raw, data["sources"]["example"])
        self.assertEqual(json.dumps(data, indent=2), before)

    def test_parse_identifies_invalid_path_and_file_hash(self):
        source = {"path": 7, "sha": "revision", "files": {"index.ts": "hash"}}
        data = {"sources": {"example": source}}
        with self.assertRaisesRegex(ValueError, "^invalid path for example$"):
            parse_sources(data)
        source["path"] = "sources/example"
        source["files"] = {"index.ts": 7}
        with self.assertRaisesRegex(ValueError, "^invalid file hash for example: index\\.ts$"):
            parse_sources(data)

    def test_materialization_rejects_non_string_revision_before_copy(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            source = root / "sources/pi-subagents"
            source.mkdir(parents=True)
            content = b"approved\n"
            (source / "index.ts").write_bytes(content)
            data = {"sources": {"pi-subagents": {
                "path": "sources/pi-subagents",
                "sha": 7,
                "files": {"index.ts": git_blob_sha(content)},
            }}}
            output = root / "build/packages"
            with self.assertRaisesRegex(ValueError, "invalid.*sha"):
                materialize(data, output, root)
            self.assertFalse(output.exists())

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
