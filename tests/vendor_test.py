import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import vendor
from tools.vendor import check, git_blob_sha, materialize, parse_sources, source_files


class VendorTests(unittest.TestCase):
    def test_command_returns_clean_output_or_raises_with_stderr(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory).resolve()
            self.assertEqual(
                vendor.command(sys.executable, "-c", "from pathlib import Path; print(Path.cwd())", cwd=root),
                str(root),
            )
            args = (
                sys.executable, "-c", "import sys; print('checkout failed', file=sys.stderr); sys.exit(17)",
                "extra argument",
            )
            with self.assertRaises(ValueError) as raised:
                vendor.command(*args, cwd=root)
            self.assertEqual(str(raised.exception), f"{' '.join(args[:3])} failed: checkout failed")

    def test_plan_reports_current_and_missing_heads_without_an_update(self):
        sources = {
            "pi-subagents": vendor.Source("sources/pi-subagents", "a" * 40, {}, {"repository": "owner/first"}),
            "pi-devin-local": vendor.Source("sources/pi-devin-local", "b" * 40, {}, {"repository": "owner/second"}),
        }
        current = "c" * 40
        with (
            patch.object(vendor, "command", side_effect=[f"{current}\trefs/heads/main", ""]) as git,
            redirect_stdout(io.StringIO()) as output,
        ):
            vendor.plan(vendor.Manifest({}, sources))
        self.assertEqual(git.call_args_list, [
            call("git", "ls-remote", "https://github.com/owner/first.git", "refs/heads/main"),
            call("git", "ls-remote", "https://github.com/owner/second.git", "refs/heads/main"),
        ])
        self.assertEqual(output.getvalue().splitlines(), [
            f"{'pi-subagents':24s} {'a' * 40} -> {current}",
            f"{'pi-devin-local':24s} {'b' * 40} -> (missing branch)",
            "Pi CLI/SDK remain track-only; rebuild and vendor the full executable/dependency closure before activation.",
        ])

    def test_cli_dispatches_after_validation(self):
        manifest = vendor.Manifest({}, {})
        for args, expected_calls in (
            (["check"], [call.check({}, vendor.ROOT)]),
            (["plan"], [call.plan(manifest)]),
            (["update", "--ref", "pi-subagents=v1.2.3"], [
                call.check({}, vendor.ROOT),
                call.update(manifest, {"pi-subagents": "v1.2.3"}),
            ]),
        ):
            with (
                self.subTest(args=args),
                patch.object(sys, "argv", ["vendor.py", *args]),
                patch.object(vendor, "load", return_value=manifest) as load,
                patch.object(vendor, "check_sources") as check,
                patch.object(vendor, "plan") as plan,
                patch.object(vendor, "update") as update,
            ):
                actions = Mock()
                actions.attach_mock(check, "check")
                actions.attach_mock(plan, "plan")
                actions.attach_mock(update, "update")
                self.assertEqual(vendor.main(), 0)
                load.assert_called_once_with()
                self.assertEqual(actions.mock_calls, expected_calls)

    def test_cli_rejects_invalid_refs_and_reports_input_errors(self):
        for args, message in (
            (["update", "--ref", "pi-subagents"], "invalid or duplicate --ref: pi-subagents"),
            (["update", "--ref", "unlisted=main"], "invalid or duplicate --ref: unlisted=main"),
            (["update", "--ref", "pi-subagents="], "invalid or duplicate --ref: pi-subagents="),
            (["update", "--ref", "pi-subagents=a", "--ref", "pi-subagents=b"],
             "invalid or duplicate --ref: pi-subagents=b"),
            (["check", "--ref", "pi-subagents=main"], "--ref is only valid with update"),
            (["plan", "--ref", "pi-subagents=main"], "--ref is only valid with update"),
        ):
            with (
                self.subTest(args=args),
                patch.object(sys, "argv", ["vendor.py", *args]),
                patch.object(vendor, "load", return_value=vendor.Manifest({}, {})),
                redirect_stderr(io.StringIO()) as error,
                self.assertRaises(SystemExit) as status,
            ):
                vendor.main()
            self.assertEqual(status.exception.code, 2)
            self.assertTrue(error.getvalue().endswith(f"error: {message}\n"), error.getvalue())

        for failure in (OSError("unavailable manifest"), ValueError("invalid manifest")):
            with (
                self.subTest(failure=failure),
                patch.object(sys, "argv", ["vendor.py", "check"]),
                patch.object(vendor, "load", side_effect=failure),
                redirect_stderr(io.StringIO()) as error,
            ):
                self.assertEqual(vendor.main(), 1)
            self.assertEqual(error.getvalue(), f"pi-vendor: {failure}\n")

    def test_cli_rejects_an_unknown_action_before_loading_sources(self):
        with (
            patch.object(sys, "argv", ["vendor.py", "unknown"]),
            patch.object(vendor, "load") as load,
            redirect_stderr(io.StringIO()) as error,
            self.assertRaises(SystemExit) as status,
        ):
            vendor.main()
        self.assertEqual(status.exception.code, 2)
        self.assertIn("invalid choice: 'unknown'", error.getvalue())
        load.assert_not_called()

    def test_isolated_vendor_cli_accepts_help(self):
        result = subprocess.run(
            [sys.executable, "-I", ROOT / "tools/vendor.py", "--help"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("{check,plan,update}", result.stdout)
        self.assertIn("--ref NAME=REF", result.stdout)
        self.assertEqual(result.stderr, "")
        with (
            patch.object(sys, "argv", ["vendor.py", "--help"]),
            redirect_stdout(io.StringIO()) as help_text,
            self.assertRaises(SystemExit) as status,
        ):
            vendor.main()
        self.assertEqual(status.exception.code, 0)
        self.assertEqual(help_text.getvalue(), result.stdout)

    def test_vendor_boundaries_report_invalid_object_and_repository(self):
        for value in (["not a mapping"], {1: "not a string key"}):
            with self.subTest(value=value), self.assertRaises(ValueError) as raised:
                vendor.object_mapping(value)
            self.assertEqual(str(raised.exception), "expected JSON object")
        with self.assertRaises(ValueError) as raised:
            vendor.repository(vendor.Source("sources/example", "a" * 40, {}, {"repository": 3}))
        self.assertEqual(str(raised.exception), "invalid upstream repository")

    def test_snapshot_diff_reports_and_bounds_each_kind(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            name = "pi-subagents"
            path = f"sources/{name}"
            revision = "a" * 40
            folder = root / path
            digest = git_blob_sha(b"verified")
            with self.assertRaises(ValueError) as raised:
                vendor.check_sources({name: vendor.Source(path, revision, {}, {})}, root)
            self.assertEqual(str(raised.exception), f"missing source directory: {folder}")
            (folder / "src").mkdir(parents=True)
            for operation in ("missing", "extra", "changed"):
                with self.subTest(operation=operation):
                    names = [f"src/{operation}-{index}.ts" for index in range(9)]
                    sources = {
                        name: vendor.Source(path, revision, {} if operation == "extra" else dict.fromkeys(names, digest), {}),
                    }
                    if operation != "missing":
                        for relative in reversed(names):
                            (folder / relative).write_bytes(b"altered")
                    with self.assertRaises(ValueError) as raised:
                        vendor.check_sources(sources, root)
                    missing = names[:8] if operation == "missing" else []
                    extra = names[:8] if operation == "extra" else []
                    changed = names[:8] if operation == "changed" else []
                    self.assertEqual(str(raised.exception), f"{name}: missing={missing}, extra={extra}, changed={changed}")
                    for relative in names:
                        (folder / relative).unlink(missing_ok=True)

    def test_materialization_rechecks_for_symlinks_after_inventory(self):
        with tempfile.TemporaryDirectory(dir=".work/tmp") as directory:
            root = Path(directory)
            name = "pi-subagents"
            path = f"sources/{name}"
            folder = root / path
            folder.mkdir(parents=True)
            data = {"sources": {name: {"path": path, "sha": "a" * 40, "files": {}}}}
            alias = folder / "alias.ts"
            check_sources = vendor.check_sources

            def check_then_add_alias(sources: dict[str, vendor.Source], snapshot_root: Path) -> None:
                check_sources(sources, snapshot_root)
                alias.symlink_to("index.ts")

            destination = root / "materialized"
            with (
                patch.object(vendor, "check_sources", side_effect=check_then_add_alias),
                redirect_stdout(io.StringIO()),
                self.assertRaises(ValueError) as raised,
            ):
                vendor.materialize(data, destination, root)
            self.assertEqual(str(raised.exception), f"symlink in upstream snapshot: {alias}")
            self.assertFalse(destination.exists())

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
            relative = "src/deep/index.ts"
            sibling = "src/deep/sibling.ts"
            (source / relative).parent.mkdir(parents=True)
            (source / relative).write_bytes(content)
            (source / sibling).write_bytes(b"export {};\n")
            (source / ".npmignore").write_text("unlisted packaging rules\n")
            data = {"sources": {"pi-subagents": {
                "path": "sources/pi-subagents",
                "sha": "0" * 40,
                "files": {relative: git_blob_sha(content), sibling: git_blob_sha(b"export {};\n")},
            }}}
            output = root / "build/packages"
            with redirect_stdout(io.StringIO()) as status:
                materialize(data, output, root)
            self.assertEqual(status.getvalue(), f"ok: pi-subagents 2 files upstream={'0' * 40}\n")
            self.assertEqual((output / "pi-subagents" / relative).read_bytes(), content)
            self.assertEqual((output / "pi-subagents" / sibling).read_bytes(), b"export {};\n")
            self.assertFalse((output / "pi-subagents/.npmignore").exists())
            (source / relative).write_text("changed after import\n")
            with self.assertRaisesRegex(ValueError, "changed"):
                check(data, root)


if __name__ == "__main__":
    unittest.main()
