"""Fetch pinned inputs with laputa-buildlib; invoked by tools/toolchain.sh.

Usage: python tools/fetch.py SOURCES_LOCK DOWNLOAD_DIR [INPUT ...]

Each INPUT names an entry in sources.lock.json. The download is published
atomically and only when its size and SHA-256 match the pin; a file that
already verifies is returned untouched.
"""

import sys
from pathlib import Path

from buildlib import locks


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    lock_path, download = Path(sys.argv[1]), Path(sys.argv[2])
    lock = locks.load_sources(lock_path)
    download.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[3:]:
        item = lock.get(name)
        destination = download / item.urls[0].rstrip("/").rsplit("/", 1)[-1]
        locks.fetch_input(item, destination)
        print(destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
