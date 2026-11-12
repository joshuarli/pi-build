import gzip
import sys
import tarfile
from pathlib import Path


def normalized(info):
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    return info


source = Path(sys.argv[1])
output = Path(sys.argv[2])
with (
    source.open("rb") as packed,
    tarfile.open(fileobj=packed, mode="r:gz") as original,
    output.open("wb") as raw,
    gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as compressed,
    tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as bundle,
):
    for member in sorted(original.getmembers(), key=lambda item: item.name):
        member.uid = member.gid = 0
        member.uname = member.gname = ""
        member.mtime = 0
        stream = original.extractfile(member) if member.isfile() else None
        bundle.addfile(member, stream)
