#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
target=$1
profile=$2
work=$root/$3
output=$root/$4
version=$5
product=pi-$profile
paths=$("$PYTHON" -c 'from pathlib import Path; import sys; root=Path(sys.argv[1]).resolve(); work=Path(sys.argv[2]).resolve(); output=Path(sys.argv[3]).resolve(); allowed_work=(root/".work").resolve(); allowed_dist=(root/"dist").resolve(); assert work.is_relative_to(allowed_work), f"build path escapes .work: {work}"; assert output.is_relative_to(allowed_dist) or output.is_relative_to(allowed_work), f"output path escapes dist/.work: {output}"; print(work); print(output)' "$root" "$work" "$output")
work=$(printf '%s\n' "$paths" | sed -n '1p')
output=$(printf '%s\n' "$paths" | sed -n '2p')
if [[ "$profile" != full ]]; then
    printf 'unsupported profile: %s\n' "$profile" >&2
    exit 2
fi
case "$target" in aarch64-apple-darwin|x86_64-unknown-linux-musl|aarch64-unknown-linux-musl) ;; *) printf 'unsupported target: %s\n' "$target" >&2; exit 2 ;; esac
lockdir=$root/locks/$target
pinned() { jaq -r --arg tool "$1" '.tools[$tool]' "$root/bootstrap.lock.json"; }
[[ "$(node --version)" == "v$(pinned node)" ]] || { printf "builder Node must be %s\n" "$(pinned node)" >&2; exit 2; }
[[ "$(npm --version)" == "$(pinned npm)" ]] || { printf "builder npm must be %s\n" "$(pinned npm)" >&2; exit 2; }
[[ "$("$PYTHON" --version)" == "Python $(pinned python)" ]] || { printf "builder Python must be %s\n" "$(pinned python)" >&2; exit 2; }
[[ "$(jaq --version)" == "jaq $(pinned jaq)" ]] || { printf "builder jaq must be %s\n" "$(pinned jaq)" >&2; exit 2; }
case "$(uname -s):$(uname -m)" in Darwin:arm64) host=aarch64-apple-darwin ;; Linux:x86_64) host=x86_64-unknown-linux-musl ;; Linux:aarch64) host=aarch64-unknown-linux-musl ;; *) printf "unsupported build host\n" >&2; exit 2 ;; esac
[[ "$target" == "$host" ]] || { printf "TARGET %s requires native host %s\n" "$target" "$target" >&2; exit 2; }
"$PYTHON" -I "$root/tools/vendor.py" check
"$PYTHON" -c 'from pathlib import Path; import shutil,sys; [shutil.rmtree(Path(p), ignore_errors=True) for p in sys.argv[1:]]' "$work/packages" "$work/runtime" "$work/tars" "$work/raw"
mkdir -p "$(dirname "$output")" "$work" "$work/home" "$work/npm-cache" "$work/packages" "$work/tars" "$work/raw" "$work/runtime" "$lockdir/tars"
export HOME="$work/home" TMPDIR="$work/tmp" npm_config_cache="$work/npm-cache"
mkdir -p "$TMPDIR"
"$PYTHON" -I -c 'import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[3]); from tools.vendor import materialize; materialize(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]),Path(sys.argv[3]))' "$root/sources/upstreams.json" "$work/packages" "$root"
(cd "$work/packages/pi-muse-subscription" && patch --silent -p1 < "$root/patches/muse-offline-catalog.patch")

jaq '.devDependencies = {"@types/node":"26.6.6","typescript":"5.9.3"} | .dependencies = {}' \
    "$work/packages/agent-intercom-core/package.json" > "$work/core-package.json"
cp "$work/core-package.json" "$work/packages/agent-intercom-core/package.json"
mkdir -p "$root/locks/core-build"
if [[ "${PREPARE_LOCKS:-0}" == 1 ]]; then
    cp "$work/packages/agent-intercom-core/package.json" "$root/locks/core-build/package.json"
    (cd "$root/locks/core-build" && npm install --package-lock-only --ignore-scripts --no-audit --no-fund)
elif [[ ! -f "$root/locks/core-build/package-lock.json" || ! -f "$root/locks/core-build/package.json" ]]; then
    printf "missing core build lock; run make prepare explicitly\n" >&2
    exit 2
fi
cp "$root/locks/core-build/package-lock.json" "$work/packages/agent-intercom-core/package-lock.json"
cp "$root/locks/core-build/.npmrc" "$work/packages/agent-intercom-core/.npmrc"
(cd "$work/packages/agent-intercom-core" && npm ci --ignore-scripts --no-audit --no-fund && ./node_modules/.bin/tsc -p tsconfig.build.json)
jaq ".dependencies = {} | .devDependencies = {} | .scripts = {}" "$work/packages/agent-intercom-core/package.json" > "$work/core-runtime-package.json"
cp "$work/core-runtime-package.json" "$work/packages/agent-intercom-core/package.json"
packed=$(cd "$work/packages/agent-intercom-core" && npm pack --silent --ignore-scripts --pack-destination "$work/raw")
"$PYTHON" -I "$root/tools/pack.py" "$work/raw/$packed" "$work/tars/core.tgz"
if [[ "${PREPARE_LOCKS:-0}" == 1 ]]; then cp "$work/tars/core.tgz" "$lockdir/tars/core.tgz"; elif ! cmp -s "$work/tars/core.tgz" "$lockdir/tars/core.tgz"; then printf "local core package differs from locked build input\n" >&2; exit 2; fi
jaq '.dependencies["@dataforxyz/agent-intercom-core"] = "0.1.0" | .scripts = {} | .devDependencies = {} | del(.peerDependencies)' \
    "$work/packages/agent-intercom-pi/package.json" > "$work/intercom-package.json"
cp "$work/intercom-package.json" "$work/packages/agent-intercom-pi/package.json"
for pair in "agent-intercom-pi intercom" "pi-subagents subagents" "pi-muse-subscription muse"; do
    set -- $pair
    packed=$(cd "$work/packages/$1" && npm pack --silent --ignore-scripts --pack-destination "$work/raw")
    "$PYTHON" -I "$root/tools/pack.py" "$work/raw/$packed" "$work/tars/$2.tgz"
    if [[ "${PREPARE_LOCKS:-0}" == 1 ]]; then cp "$work/tars/$2.tgz" "$lockdir/tars/$2.tgz"; elif ! cmp -s "$work/tars/$2.tgz" "$lockdir/tars/$2.tgz"; then printf "local package $1 differs from locked build input\n" >&2; exit 2; fi
done

cat > "$work/runtime/package.json" <<JSON
{
  "name": "usr-pi-offline-runtime",
  "private": true,
  "version": "$version",
  "type": "module",
  "dependencies": {
    "@earendil-works/pi-coding-agent": "$version",
    "@earendil-works/pi-ai": "$version",
    "@earendil-works/pi-tui": "$version",
    "@earendil-works/pi-agent-core": "$version",
    "@dataforxyz/agent-intercom-core": "file:tars/core.tgz",
    "@dataforxyz/agent-intercom-pi": "file:tars/intercom.tgz",
    "pi-subagents": "file:tars/subagents.tgz",
    "pi-muse-subscription": "file:tars/muse.tgz",
    "tsx": "4.20.6",
    "typebox": "1.3.27",
    "yaml": "2.8.3"
  },
  "overrides": {
    "@types/node": "24.19.2",
    "encodeurl": "2.0.1",
    "undici-types": "7.24.6"
  }
}
JSON
if [[ "${PREPARE_LOCKS:-0}" == 1 ]]; then
    cp "$work/runtime/package.json" "$lockdir/package.json"
    (cd "$lockdir" && "$PYTHON" -c 'from pathlib import Path; Path("package-lock.json").unlink(missing_ok=True)' && npm install --package-lock-only --ignore-scripts --no-audit --no-fund --install-strategy=hoisted)
elif [[ ! -f "$lockdir/package-lock.json" || ! -f "$lockdir/package.json" ]]; then
    printf "missing production lock; run make prepare explicitly\n" >&2
    exit 2
fi
cp "$lockdir/package.json" "$work/runtime/package.json"
cp "$lockdir/package-lock.json" "$work/runtime/package-lock.json"
cp "$lockdir/.npmrc" "$work/runtime/.npmrc"
mkdir -p "$work/runtime/tars"
cp "$lockdir/tars/"*.tgz "$work/runtime/tars/"
(cd "$work/runtime" && npm ci --omit=dev --ignore-scripts --no-audit --no-fund --install-strategy=hoisted)
node "$work/runtime/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" --version
revision=$(git -C "$root" rev-parse HEAD)
"$PYTHON" -I "$root/tools/archive.py" archive "$work/runtime" "$output" "$product" "$version" "$target" "$profile" "$revision" >/dev/null
provenance=$root/dist/$profile/provenance.json
source_digest=$(shasum -a 256 "$root/sources/upstreams.json" | awk '{print $1}')
patch_digest=$(shasum -a 256 "$root/patches/muse-offline-catalog.patch" | awk '{print $1}')
lock_digest=$(shasum -a 256 "$lockdir/package-lock.json" | awk '{print $1}')
builder_tools_digest=$(cat "$root/tools/build.sh" "$root/tools/pack.py" "$root/tools/archive.py" | shasum -a 256 | awk '{print $1}')
node_version=$(node --version)
npm_version=$(npm --version)
python_version=$("$PYTHON" --version)
jaq_version=$(jaq --version)
zlib_version=$("$PYTHON" -c 'import zlib; print(zlib.ZLIB_VERSION)')
core_lock_digest=$(shasum -a 256 "$root/locks/core-build/package-lock.json" | awk '{print $1}')
archive_sha=$(shasum -a 256 "$output" | awk '{print $1}')
archive_bytes=$(wc -c < "$output" | tr -d ' ')
if [[ -f "$provenance" ]] && ! jaq -e --arg revision "$revision" --arg profile "$profile" --arg version "$version" --arg source "$source_digest" '.builder_revision == $revision and .profile == $profile and .version == $version and .sources_sha256 == $source' "$provenance" >/dev/null; then
    "$PYTHON" -c 'from pathlib import Path; import sys; Path(sys.argv[1]).unlink(missing_ok=True)' "$provenance"
fi
if [[ ! -f "$provenance" ]]; then
    jaq -n --arg product "$product" --arg version "$version" '{schema:1,product:$product,version:$version,targets:{},inputs:{},components:{pi_coding_agent:"verified-precompiled-registry-package",intercom_core:"source-built",pi_subagents:"source-snapshot-packed",intercom_pi:"source-snapshot-packed",muse_adapter:"source-snapshot-packed+patch"}}' > "$provenance"
fi
tmp=$provenance.tmp
jaq --arg revision "$revision" --arg product "$product" --arg version "$version" --arg source "$source_digest" --arg patch "$patch_digest" --arg target "$target" --arg profile "$profile" --arg archive "$(basename "$output")" --arg sha "$archive_sha" \
    --arg lock "$lock_digest" --arg core "$core_lock_digest" --arg tools "$builder_tools_digest" --arg node "$node_version" --arg npm "$npm_version" --arg python "$python_version" --arg jaq "$jaq_version" --arg zlib "$zlib_version" --argjson bytes "$archive_bytes" \
    '.builder_revision=$revision | .profile=$profile | .product=$product | .version=$version | .sources_sha256=$source | .components //= {pi_coding_agent:"verified-precompiled-registry-package",intercom_core:"source-built",pi_subagents:"source-snapshot-packed",intercom_pi:"source-snapshot-packed",muse_adapter:"source-snapshot-packed+patch"} | .targets[$target]={target:$target,profile:$profile,archive:$archive,sha256:$sha,bytes:$bytes} | .inputs[$target]={lock_sha256:$lock,core_build_lock_sha256:$core,builder_tools_sha256:$tools,patches:{muse_offline_catalog_sha256:$patch},toolchain:{node:$node,npm:$npm,python:$python,jaq:$jaq,zlib:$zlib}}' \
    "$provenance" > "$tmp"
mv "$tmp" "$provenance"
(cd "$(dirname "$output")" && : > SHA256SUMS && for artifact in *.tar.xz; do
    [[ -f "$artifact" ]] || continue
    shasum -a 256 "$artifact" >> SHA256SUMS
done)
