"""Merge per-target build provenance into one release asset set.

Usage: python3 -I tools/release.py ASSET_DIR PROVENANCE...
Writes ASSET_DIR/provenance.json and ASSET_DIR/SHA256SUMS. Every archive the
provenance names must already be in ASSET_DIR with the recorded digest and size.
"""
import hashlib
import json
import sys
from pathlib import Path

TARGETS = ("darwin-arm64", "linux-x64", "linux-arm64")
SHARED = ("schema", "builder_revision", "profile", "sources_sha256", "components")


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            sha.update(block)
    return sha.hexdigest()


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
            if record["archive"] != f"{target}-{merged['profile']}.tar.gz":
                raise ValueError(f"unexpected archive name for {target}")
            archive = assets / record["archive"]
            if not archive.is_file() or archive.is_symlink():
                raise ValueError(f"missing archive {record['archive']}")
            if archive.stat().st_size != record["bytes"] or digest(archive) != record["sha256"]:
                raise ValueError(f"archive digest or size mismatch for {target}")
            merged["targets"][target] = record
            merged["inputs"][target] = part["inputs"][target]
    if sorted(merged["targets"]) != sorted(TARGETS):
        raise ValueError(f"release requires targets {', '.join(TARGETS)}")
    return merged


def write(assets: Path, merged: dict) -> None:
    (assets / "provenance.json").write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    lines = [f"{record['sha256']}  {record['archive']}\n" for _, record in sorted(merged["targets"].items())]
    (assets / "SHA256SUMS").write_text("".join(lines))


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
