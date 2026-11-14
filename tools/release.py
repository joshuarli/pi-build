"""Merge per-target build provenance into one release asset set.

Usage: python3 -I tools/release.py ASSET_DIR PROVENANCE...
Writes ASSET_DIR/provenance.json and ASSET_DIR/SHA256SUMS, which covers every
other file in ASSET_DIR. Every archive and manifest the provenance names must
already be in ASSET_DIR with the recorded digest and size.
"""
import json
import sys
import tarfile
from pathlib import Path

from buildlib.hashing import sha256_file
from buildlib.release import write_sha256sums
from buildlib.targets import TRIPLES as TARGETS

SHARED = ("schema", "builder_revision", "profile", "product", "version", "sources_sha256", "components", "companions")
COMPANIONS = ("agent-intercom-claude", "agent-intercom-codex", "agent-intercom-opencode")


digest = sha256_file


def merge(assets: Path, parts: list[dict]) -> dict:
    if not parts:
        raise ValueError("no provenance inputs")
    merged = {key: parts[0].get(key) for key in SHARED}
    merged["targets"], merged["inputs"] = {}, {}
    if merged["schema"] != 1:
        raise ValueError("unsupported provenance schema")
    for part in parts:
        for key in SHARED:
            if part.get(key) != merged[key]:
                raise ValueError(f"provenance {key} differs between targets")
        for target, record in part["targets"].items():
            if target in merged["targets"]:
                raise ValueError(f"duplicate target {target}")
            expected = {"target", "profile", "archive", "sha256", "bytes"}
            if set(record) != expected or record["target"] != target or record["profile"] != merged["profile"]:
                raise ValueError(f"invalid target record {target}")
            stem = f"{merged['product']}-{merged['version']}-{target}"
            if record["archive"] != f"{stem}.tar.xz":
                raise ValueError(f"unexpected archive name for {target}")
            archive = assets / record["archive"]
            if not archive.is_file() or archive.is_symlink():
                raise ValueError(f"missing archive {record['archive']}")
            if archive.stat().st_size != record["bytes"] or digest(archive) != record["sha256"]:
                raise ValueError(f"archive digest or size mismatch for {target}")
            manifest_file = assets / f"{stem}.manifest.json"
            if not manifest_file.is_file() or manifest_file.is_symlink():
                raise ValueError(f"missing manifest {manifest_file.name}")
            manifest = json.loads(manifest_file.read_text())
            if (manifest["sha256"], manifest["source_revision"]) != (record["sha256"], merged["builder_revision"]):
                raise ValueError(f"manifest differs from provenance for {target}")
            merged["targets"][target] = record
            merged["inputs"][target] = part["inputs"][target]
    companions = merged.get("companions")
    if not isinstance(companions, dict) or set(companions) != set(COMPANIONS):
        raise ValueError(f"release requires companions {', '.join(COMPANIONS)}")
    for name, record in companions.items():
        expected = {"archive", "version", "sha256", "bytes", "source_sha"}
        if set(record) != expected or not all(isinstance(value, str) for value in (record["archive"], record["version"], record["sha256"], record["source_sha"])):
            raise ValueError(f"invalid companion record {name}")
        if type(record["bytes"]) is not int or record["bytes"] <= 0:
            raise ValueError(f"invalid companion size {name}")
        archive = assets / record["archive"]
        if archive.name != record["archive"] or not archive.is_file() or archive.is_symlink():
            raise ValueError(f"missing companion archive {archive}")
        if archive.stat().st_size != record["bytes"] or digest(archive) != record["sha256"]:
            raise ValueError(f"companion archive digest or size mismatch: {name}")
        name_parts = Path(record["archive"]).parts
        if len(name_parts) != 1:
            raise ValueError(f"companion archive must not contain directories: {name}")
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            if not members:
                raise ValueError(f"companion archive is empty: {name}")
            for member in members:
                member_path = Path(member.name)
                if member.name.startswith("/") or ".." in member_path.parts:
                    raise ValueError(f"companion archive has unsafe member {member.name}: {name}")
    if sorted(merged["targets"]) != sorted(TARGETS):
        raise ValueError(f"release requires targets {', '.join(TARGETS)}")
    return merged


def write(assets: Path, merged: dict) -> None:
    (assets / "provenance.json").write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    write_sha256sums(assets)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    assets = Path(argv[1])
    parts = [json.loads(Path(path).read_text()) for path in argv[2:]]
    write(assets, merge(assets, parts))
    print(f"ok: release provenance {digest(assets / 'provenance.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
