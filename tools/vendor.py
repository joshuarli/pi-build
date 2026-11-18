#!/usr/bin/env python3
"""Audit or refresh selected upstream Pi source snapshots; never install packages."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sources/upstreams.json"
EXCLUDE = re.compile(r"(\.test\.|^test/|^\.github/|package-lock\.json|\.png$|\.jpg$|\.webp$|\.gitignore$|^dist/|^\.git(/|$))")
SUBAGENTS = re.compile(r"^(src/|agents/|docs/|skills/|prompts/|index\.ts$|.*\.mjs$|.*\.cjs$|package\.json$|LICENSE$|README\.md$)")
OTHER = re.compile(r"^(src/|broker/|ui/|provider/|skills/|index\.ts$|.*\.ts$|.*\.mjs$|.*\.cjs$|package\.json$|LICENSE$|README\.md$|COPYRIGHT$|LICENSE_TRANSITION\.md$|THIRD_PARTY_NOTICES\.md$|tsconfig(?:\.build)?\.json$)")
COMPANIONS = re.compile(r".*")
SHA = re.compile(r"[0-9a-f]{40}")
SUPPORTED = {"pi-subagents", "agent-intercom-pi", "agent-intercom-core", "pi-muse-subscription",
             "agent-intercom-claude", "agent-intercom-codex", "agent-intercom-opencode", "pi-devin-local"}


def source_files(folder: Path, name: str) -> list[Path]:
    if name == "pi-subagents":
        pattern = SUBAGENTS
    elif name in {"agent-intercom-claude", "agent-intercom-codex", "agent-intercom-opencode"}:
        pattern = COMPANIONS
    else:
        pattern = OTHER
    result = []
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink in upstream snapshot: {path}")
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            if not EXCLUDE.search(relative) and pattern.search(relative):
                result.append(path)
    return sorted(result)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}".encode() + bytes([0]) + data).hexdigest()


@dataclass
class Source:
    path: str
    sha: str
    files: dict[str, str]
    raw: dict[str, object]


@dataclass
class Manifest:
    raw: dict[str, object]
    sources: dict[str, Source]


def is_object_mapping(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def object_mapping(value: object) -> dict[str, object]:
    if not is_object_mapping(value):
        raise ValueError("expected JSON object")
    return value


def string_field(value: object, label: str) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"invalid {label}")


def parse_sources(data: object) -> dict[str, Source]:
    raw_sources = object_mapping(object_mapping(data).get("sources"))
    sources: dict[str, Source] = {}
    for name, value in raw_sources.items():
        src = object_mapping(value)
        path = string_field(src.get("path"), f"path for {name}")
        sha = string_field(src.get("sha"), f"sha for {name}")
        raw_files = object_mapping(src.get("files"))
        files: dict[str, str] = {}
        for relative, digest in raw_files.items():
            files[relative] = string_field(digest, f"file hash for {name}: {relative}")
        sources[name] = Source(path, sha, files, src)
    return sources


def load() -> Manifest:
    data = object_mapping(json.loads(MANIFEST.read_text()))
    sources = parse_sources(data)
    if data.get("schema") != 1 or set(sources) != SUPPORTED:
        raise ValueError("unsupported or incomplete Pi vendor manifest")
    for name, src in sources.items():
        if src.path != f"sources/{name}" or not SHA.fullmatch(src.sha):
            raise ValueError(f"invalid identity for {name}")
        repository = src.raw.get("repository")
        if not isinstance(repository, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repository):
            raise ValueError(f"invalid upstream repository for {name}")
        if not src.files:
            raise ValueError(f"empty source inventory for {name}")
        if any(not SHA.fullmatch(sha) for sha in src.files.values()):
            raise ValueError(f"invalid upstream file hashes for {name}")
    return Manifest(data, sources)


def check_sources(sources: dict[str, Source], root: Path) -> None:
    for name, src in sources.items():
        folder = root / src.path
        if not folder.is_dir():
            raise ValueError(f"missing source directory: {folder}")
        expected = src.files
        actual = {p.relative_to(folder).as_posix(): git_blob_sha(p.read_bytes())
                  for p in source_files(folder, name)}
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        modified = sorted(k for k in actual.keys() & expected.keys() if actual[k] != expected[k])
        if missing or extra or modified:
            raise ValueError(f"{name}: missing={missing[:8]}, extra={extra[:8]}, changed={modified[:8]}")
        print(f"ok: {name} {len(actual)} files upstream={src.sha}")


def check(data: object, root: Path = ROOT) -> None:
    check_sources(parse_sources(data), root)


def materialize(data: object, destination: Path, root: Path = ROOT) -> None:
    """Copy only manifest-listed, verified files into a clean build input tree."""
    sources = parse_sources(data)
    check_sources(sources, root)
    for name, src in sources.items():
        folder = root / src.path
        for path in folder.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"symlink in upstream snapshot: {path}")
        output = destination / name
        output.mkdir(parents=True)
        for relative in sorted(src.files):
            source = folder / relative
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def command(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"{' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def repository(src: Source) -> str:
    return string_field(src.raw.get("repository"), "upstream repository")


def plan(data: Manifest) -> None:
    for name, src in data.sources.items():
        remote = f"https://github.com/{repository(src)}.git"
        current = command("git", "ls-remote", remote, "refs/heads/main")
        new_sha = current.split()[0] if current else "(missing branch)"
        print(f"{name:24s} {src.sha} -> {new_sha}")
    print("Pi CLI/SDK remain track-only; rebuild and vendor the full executable/dependency closure before activation.")


def update(data: Manifest, refs: dict[str, str]) -> None:
    # This operation updates source *only*. It does not activate a runtime.
    state = command("git", "status", "--porcelain", "--", "sources", cwd=ROOT)
    if state:
        raise ValueError("sources has uncommitted changes; refusing to overwrite them")
    staged = copy.deepcopy(data.raw)
    sources = parse_sources(staged)
    with tempfile.TemporaryDirectory(prefix=".pi-update-", dir=ROOT / "sources") as temp:
        temp_root = Path(temp)
        for name, src in sources.items():
            remote = f"https://github.com/{repository(src)}.git"
            ref = refs.get(name, "main")
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref) or ref.startswith("-") or ".." in ref:
                raise ValueError(f"unsafe ref: {ref}")
            checkout = temp_root / f"{name}-checkout"
            command("git", "clone", "--quiet", "--depth=1", "--filter=blob:none",
                    "--branch", ref, remote, str(checkout))
            upstream_sha = command("git", "rev-parse", "HEAD", cwd=checkout)
            if not SHA.fullmatch(upstream_sha):
                raise ValueError(f"invalid upstream revision for {name}")
            output = temp_root / f"{name}-new"
            output.mkdir()
            upstream_files = source_files(checkout, name)
            if not upstream_files:
                raise ValueError(f"no source files for {name}")
            hashes = {}
            for file in upstream_files:
                relative = file.relative_to(checkout)
                target = output / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
                hashes[relative.as_posix()] = git_blob_sha(file.read_bytes())
            package = object_mapping(json.loads((output / "package.json").read_text()))
            src.raw.update(sha=upstream_sha, ref=ref, version=package["version"],
                       files=dict(sorted(hashes.items())))
        proposed = temp_root / "upstreams.json.tmp"
        proposed.write_text(json.dumps(staged, indent=2) + "\n")
        backup_root = Path(tempfile.mkdtemp(prefix=".pi-backup-", dir=ROOT / "sources"))
        backups: list[tuple[Path, Path]] = []
        try:
            for name, src in sources.items():
                destination = ROOT / src.path
                backup = backup_root / f"{name}-previous"
                backups.append((destination, backup))
                os.replace(destination, backup)
                os.replace(temp_root / f"{name}-new", destination)
            check(staged, ROOT)
            os.replace(proposed, MANIFEST)
        except BaseException:
            # The atomic replacement consumes the proposed file when it commits.
            if proposed.exists():
                for destination, backup in reversed(backups):
                    if backup.exists():
                        if destination.exists():
                            shutil.rmtree(destination)
                        os.replace(backup, destination)
            shutil.rmtree(backup_root)
            raise
        shutil.rmtree(backup_root)
    print("Source snapshots refreshed. NOT a runtime/SDK update; run /pi-update gates before integration.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "plan", "update"])
    parser.add_argument("--ref", action="append", default=[], metavar="NAME=REF",
                        help="Select a compatible upstream branch/tag for a source (update only)")
    args = parser.parse_args()
    refs = {}
    for assignment in args.ref:
        name, sep, ref = assignment.partition("=")
        if not sep or name not in SUPPORTED or not ref or name in refs:
            parser.error(f"invalid or duplicate --ref: {assignment}")
        refs[name] = ref
    try:
        data = load()
        if args.action == "check":
            if refs:
                parser.error("--ref is only valid with update")
            check_sources(data.sources, ROOT)
        elif args.action == "plan":
            if refs:
                parser.error("--ref is only valid with update")
            plan(data)
        else:
            check_sources(data.sources, ROOT)
            update(data, refs)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"pi-vendor: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
