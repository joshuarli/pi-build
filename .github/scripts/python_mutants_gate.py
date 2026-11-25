from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_TEST = "tests/package_tools_test.py"
VENDOR_TEST = "tests/vendor_test.py"
ARCHIVE_TEST = "tests/archive_test.py"
TESTS = {
    "archive": (ARCHIVE_TEST,),
    "fetch": (PACKAGE_TEST,),
    "intercom": ("tests/intercom_overlay_test.py",),
    "pack": (PACKAGE_TEST,),
    "release": ("tests/release_test.py",),
    "sizes": ("tests/sizes_test.py",),
    "vendor": (VENDOR_TEST, "tests/vendor_update_test.py"),
}
SOURCES = {f"tools/{module}.py": module for module in TESTS}
SHARED = {
    ".gitignore", "Makefile", "pyproject.toml", "uv.lock",
    "bootstrap.lock.json", "sources.lock.json", ".github/workflows/ci.yml",
    ".github/workflows/lint.yml", ".github/workflows/prepare-locks.yml", ".github/workflows/release.yml",
    ".github/workflows/python-mutation.yml", ".github/scripts/python_mutants_gate.py",
    ".github/scripts/python_mutation_receipts.json", ".github/tools.lock.json",
}
CLIS = {
    PACKAGE_TEST: tuple((f'TOOLS / "{name}.py"', f'ROOT / "cli-proof/{name}.py"') for name in ("fetch", "pack")),
    VENDOR_TEST: (('ROOT / "tools/vendor.py", "--help"', 'ROOT / "cli-proof/vendor.py", "--help"'),),
}
BUILD_TOOLS = {
    "tools/build.sh", "tools/compile-devin.mjs", "tools/headless.mjs", "tools/patch-pi-help.mjs",
    "tools/test-intercom.mjs", "tools/toolchain.sh", "tools/verify-companions.mjs",
    "tools/verify-providers.mjs", "tools/verify.mjs",
    "tests/intercom-tailnet-policy.test.mjs", "tests/intercom-tailnet-transport.test.mjs",
    "tests/pi-help.test.mjs", "tests/verify-companions.test.mjs",
}
CYCLE = "tools.archive.x_validate_members__mutmut_67"


def select(changes: dict[str, str]) -> set[str]:
    selected: set[str] = set()
    for path, status in sorted(changes.items()):
        if status == "U":
            raise ValueError(f"unmerged path: {path}")
        if path in SOURCES:
            if status in ("D", "T"):
                raise ValueError(f"missing or replaced Python source: {path}")
            selected.add(SOURCES[path])
            if path == "tools/vendor.py":
                selected.add("intercom")
        elif path in SHARED or path in BUILD_TOOLS or path.startswith(("locks/", "patches/", "overlays/")):
            selected.update(TESTS)
        elif path.startswith("sources/"):
            selected.update(("archive", "intercom", "vendor"))
        else:
            affected = {module for module, tests in TESTS.items() if path in tests}
            if not affected and not path.endswith(".md"):
                raise ValueError(f"unqualified change: {path}")
            selected.update(affected)
    return selected


def seal(directory: Path, module: str) -> None:
    for path in (*SOURCES, *TESTS[module], "sources.lock.json", "sources/upstreams.json"):
        destination = directory / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
    cli_sources = ()
    if PACKAGE_TEST in TESTS[module]:
        cli_sources = ("fetch", "pack")
    elif VENDOR_TEST in TESTS[module]:
        cli_sources = ("vendor",)
    for name in cli_sources:
        script = directory / "cli-proof" / f"{name}.py"
        script.parent.mkdir(exist_ok=True)
        shutil.copyfile(directory / "tools" / script.name, script)
    for test in TESTS[module]:
        if test in CLIS:
            path = directory / test
            text = path.read_text()
            for original, pristine in CLIS[test]:
                text = text.replace(original, pristine)
            path.write_text(text)
    extra_files = [path for path in SOURCES if path != f"tools/{module}.py"]
    extra_files += ["sources.lock.json", "sources/upstreams.json"]
    if cli_sources:
        extra_files.append("cli-proof/")
    (directory / "pyproject.toml").write_text(
        '[tool.mutmut]\nsource_paths = ["tools/"]\n'
        f'only_mutate = ["tools/{module}.py"]\n'
        f'pytest_add_cli_args_test_selection = {json.dumps(TESTS[module])}\n'
        f'also_copy = {json.dumps(extra_files)}\n'
        'use_setproctitle = false\ntimeout_constant = 5.0\n',
    )
    (directory / "mutants/.work/tmp").mkdir(parents=True)
    (directory / "mutants/sources").mkdir(parents=True)
    (directory / ".work/tmp").mkdir(parents=True)


def verify_archive_cycle(directory: Path) -> None:
    script = directory / "tools/archive.py"
    source = script.read_text()
    if source.count("seen.add(target)") != 1:
        raise ValueError("archive cycle witness changed")
    script.write_text(source.replace("seen.add(target)", "seen.add(None)"))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         f"{ARCHIVE_TEST}::ArchiveTests::test_member_validator_reports_a_chain_leading_into_a_cycle"],
        cwd=directory, capture_output=True, text=True, check=False, timeout=15,
    )
    if result.returncode != 1 or "subprocess.TimeoutExpired" not in result.stdout:
        raise ValueError(f"bounded archive cycle control did not fail as expected:\n{result.stdout}{result.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", type=Path)
    admission = parser.add_mutually_exclusive_group(required=True)
    admission.add_argument("--base")
    admission.add_argument("--all-python", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("buildlib_gate", args.engine)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.__dict__["ROOT"] = ROOT
    selected = set(TESTS) if args.all_python else select(gate.git_changes(args.base))
    print("selected Python modules", sorted(selected), flush=True)
    receipts = gate.load_json(ROOT / ".github/scripts/python_mutation_receipts.json")
    deadline = time.monotonic() + 500
    failures: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="pi-python-trial-", dir=os.environ["TMPDIR"]) as temporary:
        for module in sorted(selected):
            directory = Path(temporary) / module
            seal(directory, module)
            prefix = f"tools.{module}."
            gate.run_command([sys.executable, "-m", "mutmut", "run", "--max-children", "1", prefix + "*"], directory, deadline)
            mutated = directory / f"mutants/tools/{module}.py"
            spans = mutated.with_suffix(".py.spans")
            results = gate.read_results(mutated.with_suffix(".py.meta"), spans, prefix)
            print(module, "tested", len(results), "identities", flush=True)
            expected = receipts.get(module, {})
            approved = gate.qualified_survivors(directory / f"tools/{module}.py", mutated, spans, prefix, expected)
            pending = {
                name: status for name, status in results.items()
                if status != "killed" and (status != "survived" or name not in approved)
            }
            if pending:
                failures[module] = pending
            if CYCLE in approved:
                verify_archive_cycle(directory)
            print(module, "approved survivors", sorted(name for name in approved if results[name] != "killed"), flush=True)
    if failures:
        raise ValueError(f"unqualified Python mutations: {failures}")


if __name__ == "__main__":
    main()
