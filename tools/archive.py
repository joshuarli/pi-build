import hashlib
import json
import lzma
import posixpath
import tarfile
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def manifest_path(archive_path):
    path = Path(archive_path)
    return path.with_name(path.name.removesuffix(".tar.xz") + ".manifest.json")


def archive(source, output, product, version, target, profile, source_revision):
    root = Path(source)
    output = Path(output)
    modules = root / "node_modules"
    with (
        output.open("wb") as raw,
        lzma.LZMAFile(raw, "wb", format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=9) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as bundle,
    ):
        for path in sorted(modules.rglob("*"), key=lambda item: item.relative_to(modules).as_posix()):
            relative = path.relative_to(modules).as_posix()
            info = bundle.gettarinfo(str(path), arcname="node_modules/" + relative)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if info.isfile():
                with path.open("rb") as stream:
                    bundle.addfile(info, stream)
            else:
                bundle.addfile(info)
    inventory = {}
    for package in sorted((root / "node_modules").iterdir()):
        if package.name.startswith("@"):
            for scoped in sorted(package.iterdir()):
                inventory[package.name + "/" + scoped.name] = sum(p.stat().st_size for p in scoped.rglob("*") if p.is_file() and not p.is_symlink())
        else:
            inventory[package.name] = sum(p.stat().st_size for p in package.rglob("*") if p.is_file() and not p.is_symlink())
    manifest = {
        "schema_version": 1,
        "product": product,
        "version": version,
        "target": target,
        "profile": profile,
        "source_revision": source_revision,
        "sources_lock_sha256": digest(Path("sources.lock.json")),
        "archive": output.name,
        "sha256": digest(output),
        "bytes": output.stat().st_size,
        "source_manifest_sha256": digest(Path("sources/upstreams.json")),
        "packages": inventory,
    }
    manifest_path(output).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
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
