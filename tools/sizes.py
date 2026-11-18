import json
import sys
from pathlib import Path


def main() -> None:
    profile = sys.argv[1]
    for path in sorted(Path("dist", profile).glob("*.tar.xz")):
        manifest = json.loads(path.with_name(path.name.removesuffix(".tar.xz") + ".manifest.json").read_text())
        print(f"{manifest['target']} compressed={manifest['bytes']} payload={sum(manifest['packages'].values())}")


if __name__ == "__main__":
    main()
