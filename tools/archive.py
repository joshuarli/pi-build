import json
import posixpath
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path

from buildlib.hashing import sha256_file
from buildlib.release import build_manifest, create_archive, write_manifest

HEADLESS_EXCLUSIONS = ("*.map", "*.d.ts", "*.d.mts", "*.d.cts")


def digest(path):
    return sha256_file(Path(path))


def _inventory(root: Path) -> dict[str, int]:
    inventory: dict[str, int] = {}
    modules = root / "node_modules"
    for path in modules.rglob("*"):
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            continue
        parts = path.relative_to(modules).parts
        package = "/".join(parts[:2]) if parts[0].startswith("@") else parts[0]
        inventory[package] = inventory.get(package, 0) + metadata.st_size
    return inventory


def archive(source, output, product, version, target, profile, source_revision):
    if profile not in {"full", "headless-usr"}:
        raise ValueError(f"unsupported profile: {profile}")
    root = Path(source)
    output = Path(output)
    if profile == "headless-usr":
        with tempfile.TemporaryDirectory(prefix="headless-usr-", dir=root.parent) as staging:
            staged = Path(staging) / "root"
            shutil.copytree(root, staged, symlinks=True, ignore=shutil.ignore_patterns(*HEADLESS_EXCLUSIONS))
            return _assemble(staged, output, product, version, target, profile, source_revision)
    return _assemble(root, output, product, version, target, profile, source_revision)


def _assemble(root, output, product, version, target, profile, source_revision):
    output.parent.mkdir(parents=True, exist_ok=True)
    create_archive(root, output, mtime=0)
    manifest = build_manifest(
        product=product,
        version=version,
        target=target,
        source_revision=source_revision,
        sources_lock_sha256=sha256_file(Path("sources.lock.json")),
        extra={
            "archive": output.name,
            "bytes": output.stat().st_size,
            "packages": _inventory(root),
            "profile": profile,
            "sha256": sha256_file(output),
            "source_manifest_sha256": sha256_file(Path("sources/upstreams.json")),
        },
    )
    write_manifest(output.parent, manifest)
    return manifest


def verify(archive_path, manifest_path, target, profile):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest["schema_version"] != 1 or manifest["target"] != target or manifest["profile"] != profile:
        raise ValueError("artifact identity mismatch")
    if manifest["bytes"] != Path(archive_path).stat().st_size or manifest["sha256"] != digest(Path(archive_path)):
        raise ValueError("archive digest or size mismatch")
    with tarfile.open(archive_path, "r:xz") as bundle:
        validate_members(bundle.getmembers())
    return manifest


def validate_members(members):
    names = set()
    links = {}
    for member in members:
        path = Path(member.name)
        if member.name in names:
            raise ValueError("duplicate archive member: " + member.name)
        names.add(member.name)
        if not path.parts or path.parts[0] != "node_modules" or path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir() or member.issym()):
            raise ValueError("unsafe archive member: " + member.name)
        if member.issym():
            if Path(member.linkname).is_absolute():
                raise ValueError("unsafe archive link: " + member.name)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
            if target == ".." or target.startswith("../"):
                raise ValueError("unsafe archive link: " + member.name)
            links[member.name] = target
    for name in names:
        parent = posixpath.dirname(name)
        while parent:
            if parent in links:
                raise ValueError("archive member traverses symlink parent: " + name)
            parent = posixpath.dirname(parent)
    for name, target in links.items():
        seen = {name}
        while target in links:
            if target in seen:
                raise ValueError("cyclic archive link: " + name)
            seen.add(target)
            target = links[target]
        if target not in names:
            raise ValueError("dangling archive link: " + name)


def unpack(source, destination):
    with tarfile.open(source, "r:xz") as bundle:
        members = bundle.getmembers()
        validate_members(members)
        bundle.extractall(destination, members=members)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("archive")
    pack.add_argument("source")
    pack.add_argument("output")
    pack.add_argument("product")
    pack.add_argument("version")
    pack.add_argument("target")
    pack.add_argument("profile")
    pack.add_argument("source_revision")
    unpacker = commands.add_parser("unpack")
    unpacker.add_argument("archive")
    unpacker.add_argument("destination")
    check = commands.add_parser("verify")
    check.add_argument("archive")
    check.add_argument("manifest")
    check.add_argument("target")
    check.add_argument("profile")
    args = parser.parse_args()
    if args.command == "archive":
        print(json.dumps(archive(args.source, args.output, args.product, args.version, args.target, args.profile, args.source_revision), sort_keys=True))
    elif args.command == "unpack":
        unpack(args.archive, args.destination)
    else:
        print(json.dumps(verify(args.archive, args.manifest, args.target, args.profile), sort_keys=True))
