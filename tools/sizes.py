import argparse
import json
import math
import sys
import tarfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive import validate_members, verify


def artifacts(directory: Path, profile: str) -> dict[str, dict[str, Any]]:
    paths = sorted(directory.glob("*.tar.xz"))
    if not paths:
        raise ValueError(f"no archives in {directory}")
    for manifest_path in directory.glob("*.manifest.json"):
        archive_path = manifest_path.with_name(manifest_path.name.removesuffix(".manifest.json") + ".tar.xz")
        if not archive_path.is_file():
            raise ValueError(f"missing archive: {archive_path}")
    result = {}
    for path in paths:
        manifest_path = path.with_name(path.name.removesuffix(".tar.xz") + ".manifest.json")
        manifest = json.loads(manifest_path.read_text())
        target = manifest["target"]
        if (not isinstance(target, str) or not target or manifest["profile"] != profile
                or manifest["archive"] != path.name
                or path.name != f"{manifest['product']}-{manifest['version']}-{target}.tar.xz"):
            raise ValueError(f"artifact identity mismatch: {path}")
        if target in result:
            raise ValueError(f"duplicate target: {target}")
        packages = manifest["packages"]
        if not isinstance(packages, dict) or any(
            not isinstance(name, str) or type(size) is not int or size < 0
            for name, size in packages.items()
        ):
            raise ValueError(f"invalid package sizes: {manifest_path}")
        if type(manifest["bytes"]) is not int or manifest["bytes"] < 0:
            raise ValueError(f"invalid archive size: {manifest_path}")
        if "sha256" in manifest:
            verify(path, manifest_path, target, profile)
        else:
            if manifest["schema_version"] != 1 or manifest["bytes"] != path.stat().st_size:
                raise ValueError(f"archive identity or size mismatch: {path}")
            with tarfile.open(path, "r:xz") as bundle:
                validate_members(bundle.getmembers())
        result[target] = manifest
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile")
    parser.add_argument("reference", nargs="?", type=Path)
    parser.add_argument("--threshold", type=float, default=5.0)
    args = parser.parse_args()
    if not math.isfinite(args.threshold) or args.threshold < 0:
        parser.error("threshold must be a finite nonnegative percentage")
    try:
        candidate = artifacts(Path("dist") / args.profile, args.profile)
        if args.reference is None:
            for target, manifest in candidate.items():
                print(f"{target} compressed={manifest['bytes']} payload={sum(manifest['packages'].values())}")
            return 0
        reference = artifacts(args.reference, args.profile)
        if candidate.keys() != reference.keys():
            raise ValueError(f"target pairs mismatch: reference only={sorted(reference.keys() - candidate.keys())}, candidate only={sorted(candidate.keys() - reference.keys())}")
        grew = False
        for target in sorted(candidate):
            old, new = reference[target], candidate[target]
            old_payload, new_payload = sum(old["packages"].values()), sum(new["packages"].values())
            print(f"{target} compressed={old['bytes']} -> {new['bytes']} ({new['bytes'] - old['bytes']:+d}) payload={old_payload} -> {new_payload} ({new_payload - old_payload:+d})")
            for name, size in sorted(new["packages"].items()):
                previous = old["packages"].get(name, 0)
                if size > previous:
                    print(f"  {name}: {previous} -> {size} (+{size - previous})")
            grew |= any(new_size > old_size * (1 + args.threshold / 100) for old_size, new_size in ((old["bytes"], new["bytes"]), (old_payload, new_payload)))
        return int(grew)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print(f"sizes: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
