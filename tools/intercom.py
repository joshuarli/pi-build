#!/usr/bin/env python3
"""Apply reviewed Intercom changes to a verified, disposable source tree.

The upstream snapshots and their blob inventory stay unchanged. Both native
builds and the network-free protocol fixtures consume this same patch series.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ("intercom-tailnet-policy.patch", "intercom-tailnet-transport.patch")


def inputs(root: Path = ROOT) -> list[Path]:
    files = [root / "patches" / name for name in PATCHES]
    overlay = root / "overlays"
    files.extend(sorted(path for path in overlay.rglob("*") if path.is_file()))
    if any(path.is_symlink() or not path.is_file() for path in files):
        raise ValueError("Intercom patches and overlays must be regular files")
    return files


def digest(root: Path = ROOT) -> str:
    result = hashlib.sha256()
    for path in inputs(root):
        result.update(path.relative_to(root).as_posix().encode() + b"\0")
        result.update(path.read_bytes() + b"\0")
    return result.hexdigest()


def apply(destination: Path, root: Path = ROOT) -> None:
    destination = destination.resolve(strict=True)
    if destination == (root / "sources").resolve() or not destination.is_relative_to((root / ".work").resolve()):
        raise ValueError("Intercom changes may only be applied to a copied tree under .work")
    files = inputs(root)
    for path in files[:len(PATCHES)]:
        with path.open("rb") as patch:
            subprocess.run(
                ["patch", "--batch", "--forward", "--fuzz=0", "-p1"],
                input=patch.read(), cwd=destination, check=True,
            )
    for path in files[len(PATCHES):]:
        target = destination / path.relative_to(root / "overlays")
        if target.exists() or target.is_symlink():
            raise ValueError(f"Intercom overlay would replace an upstream file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def prepare(destination: Path, root: Path = ROOT) -> None:
    """Materialize an entirely new disposable tree; never update a snapshot."""
    destination = destination.resolve()
    work = (root / ".work").resolve()
    if destination == work or not destination.is_relative_to(work):
        raise ValueError("prepared Intercom sources must be under .work")
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    sys.path.insert(0, str(root))
    from tools.vendor import materialize
    materialize(json.loads((root / "sources/upstreams.json").read_text()), destination, root)
    apply(destination, root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("digest")
    for name in ("apply", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "digest":
        print(digest())
    elif args.command == "apply":
        apply(args.destination)
    else:
        prepare(args.destination)


if __name__ == "__main__":
    main()
