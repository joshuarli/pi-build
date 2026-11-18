from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "tools/archive.py"
TEST = "tests/archive_test.py"
INPUTS = {"sources.lock.json", "sources/upstreams.json"}
CONFIGURATION = {
    "Makefile", "pyproject.toml", "uv.lock",
    ".github/scripts/archive_change_trial.py",
    ".github/scripts/archive_mutation_receipt.json",
    ".github/workflows/archive-change-trial.yml",
}
EXPECTED_DELETION = "tools.archive.x_archive__mutmut_6"
CYCLE = "tools.archive.x_validate_members__mutmut_67"


def select(changes: dict[str, str]) -> set[str]:
    selected = set()
    for path, kind in changes.items():
        if kind == "U":
            raise ValueError(f"unmerged change: {path}")
        if path in {SOURCE, TEST} | INPUTS | CONFIGURATION:
            if path == SOURCE and kind == "D":
                raise ValueError(f"deleted production input: {path}")
            selected.add(SOURCE)
        elif not path.endswith(".md"):
            raise ValueError(f"unqualified change: {path}")
    return selected


def run_git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def seal(root: Path) -> str:
    for path in (SOURCE, TEST, *sorted(INPUTS)):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    (root / ".gitignore").write_text(".work/\nmutants/\n__pycache__/\n")
    (root / "pyproject.toml").write_text("""
[tool.mutmut]
source_paths = ["tools/"]
pytest_add_cli_args_test_selection = ["tests/archive_test.py"]
also_copy = ["sources.lock.json", "sources/upstreams.json"]
use_setproctitle = false
timeout_constant = 5.0
""".lstrip())
    run_git(root, "init", "-q")
    run_git(root, "add", ".")
    run_git(root, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "seal")
    return run_git(root, "rev-parse", "HEAD")


def edit(root: Path, case: str) -> set[str]:
    test = root / TEST
    if case == "docs":
        (root / "README.md").write_text("Archive fixture documentation.\n")
        return {"README.md"}
    if case == "unknown":
        (root / "tools/unqualified.py").write_text("VALUE = 1\n")
        return {"tools/unqualified.py"}
    if case == "positive":
        test.write_text(test.read_text() + "\n")
        return {TEST}
    text = test.read_text()
    classes = [node for node in ast.parse(text).body if isinstance(node, ast.ClassDef)]
    removed = next(
        node for cls in classes for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "test_archive_rejects_unknown_profile_before_creating_output"
    )
    assert removed.end_lineno is not None
    lines = text.splitlines(keepends=True)
    del lines[removed.lineno - 1:removed.end_lineno]
    test.write_text("".join(lines))
    if case == "mixed":
        source = root / SOURCE
        original = "    return sha256_file(Path(path))"
        data = source.read_text()
        assert data.count(original) == 1
        source.write_text(data.replace(original, "    archive_path = Path(path)\n    return sha256_file(archive_path)"))
        return {TEST, SOURCE}
    return {TEST}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", type=Path)
    parser.add_argument("case", choices=("event", "positive", "deletion", "mixed", "docs", "unknown"))
    parser.add_argument("--base")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("buildlib_gate", args.engine)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    with tempfile.TemporaryDirectory(prefix="archive-trial-", dir=os.environ["TMPDIR"]) as scratch:
        root = Path(scratch)
        if args.case == "event":
            if args.base is None:
                parser.error("--base is required when checking a pull request")
            gate.ROOT = ROOT
            changes = gate.git_changes(args.base)
        else:
            base = seal(root)
            expected = edit(root, args.case)
            gate.ROOT = root
            changes = gate.git_changes(base)
            assert set(changes) == expected, changes
        print(args.case, "changed paths", sorted(changes), flush=True)
        if args.case == "unknown":
            try:
                select(changes)
            except ValueError as error:
                assert str(error) == "unqualified change: tools/unqualified.py"
                print(error)
                return
            raise AssertionError("an unsupported path was accepted")
        selected = select(changes)
        if args.case != "event":
            assert selected == (set() if args.case == "docs" else {SOURCE}), selected
        print("selected", sorted(selected), flush=True)
        if not selected:
            return

        if args.case == "event":
            seal(root)
        (root / "mutants/sources").mkdir(parents=True)
        (root / "mutants/.work/tmp").mkdir(parents=True)
        (root / ".work/tmp").mkdir(parents=True)
        subprocess.run(
            [sys.executable, "-m", "mutmut", "run", "--max-children", "1", "tools.archive.*"],
            cwd=root, check=True, timeout=120,
        )
        artifact = root / "mutants/tools/archive.py"
        spans = artifact.with_suffix(".py.spans")
        results = gate.read_results(artifact.with_suffix(".py.meta"), spans, "tools.archive.")
        print("tested", len(results), "identities", flush=True)
        if args.case == "mixed":
            assert any(name.startswith("tools.archive.x_digest__mutmut_") for name in results)
        elif args.case != "event":
            assert len(results) == 268
        receipt = json.loads((ROOT / ".github/scripts/archive_mutation_receipt.json").read_text())
        approved = gate.qualified_survivors(root / SOURCE, artifact, spans, "tools.archive.", receipt)
        surviving = {name for name, outcome in results.items() if outcome == "survived"}
        assert set(results.values()) <= {"killed", "survived"}, results
        unexpected = surviving - approved
        if args.case in ("deletion", "mixed"):
            assert EXPECTED_DELETION in unexpected, unexpected
            print("rejected control with surviving", EXPECTED_DELETION, flush=True)
            return
        assert not unexpected, unexpected
        assert CYCLE in approved
        module = root / SOURCE
        original = module.read_text()
        assert hashlib.sha256(module.read_bytes()).hexdigest() == receipt["source_sha256"]
        assert original.count("seen.add(target)") == 1
        module.write_text(original.replace("seen.add(target)", "seen.add(None)"))
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"{TEST}::ArchiveTests::test_member_validator_reports_a_chain_leading_into_a_cycle"],
            cwd=root, capture_output=True, text=True, check=False, timeout=15,
        )
        assert result.returncode == 1 and "subprocess.TimeoutExpired" in result.stdout, result.stdout + result.stderr
        print("bounded cycle control failed as expected", flush=True)
        print("reconciled archive change", sorted(surviving), flush=True)


if __name__ == "__main__":
    main()
