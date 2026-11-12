import json
import sys
from pathlib import Path

profile = sys.argv[1]
for path in sorted(Path("dist", profile).glob("*.tar.gz")):
    manifest = json.loads(Path(str(path) + ".manifest.json").read_text())
    print(f"{manifest['target']} compressed={manifest['bytes']} payload={sum(manifest['packages'].values())}")
