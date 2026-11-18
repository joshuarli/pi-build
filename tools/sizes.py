import json
import sys
from pathlib import Path


def main() -> None:
    profile = sys.argv[1]
    artifacts = sorted(Path("dist", profile).glob("*.tar.xz"))
    for path in artifacts:
        manifest = json.loads(path.with_name(path.name.removesuffix(".tar.xz") + ".manifest.json").read_text())
        print(f"{manifest['target']} compressed={manifest['bytes']} payload={sum(manifest['packages'].values())}")


if __name__ == "__main__":
    main()
