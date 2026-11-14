#!/bin/sh
# Usage: sh tools/toolchain.sh TARGET [musl]
# Installs digest-verified builder tools under .work/toolchain/TARGET and
# prints their bin directory followed by the Python interpreter path.
# With musl, installs only the Alpine musl Node used for loader checks under
# .work/toolchain/TARGET-check and prints its bin directory.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
target=$1
mode=${2:-build}
sources=$root/sources.lock.json
bootstrap=$root/bootstrap.lock.json
dest=$root/.work/toolchain/$target
[ "$mode" = musl ] && dest=$dest-check

digest() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

fetch() {
    file=$1
    url=$2
    sha=$3
    rm -f "$file" "$file.part"
    curl -fsSL --retry 3 -o "$file.part" "$url"
    actual=$(digest "$file.part")
    [ "$actual" = "$sha" ] || { printf '%s: sha256 %s, expected %s\n' "$url" "$actual" "$sha" >&2; rm -f "$file.part"; exit 1; }
    mv "$file.part" "$file"
}

jaq=$root/.work/toolchain/$target/jaq/jaq
if [ ! -x "$jaq" ]; then
    jaq=$(command -v jaq || true)
fi
if [ -z "$jaq" ]; then
    jaq=$root/.work/toolchain/$target/jaq/jaq
    boot=$(awk -v name="jaq-$target" '
        $1 == "\"name\":" { entry = ($2 == "\"" name "\",") }
        entry && $1 == "\"url\":" { url = $2; gsub(/[",]/, "", url) }
        entry && $1 == "\"sha256\":" { sha = $2; gsub(/[",]/, "", sha); print url, sha; exit }
    ' "$sources")
    [ -n "$boot" ] || { printf 'no jaq input for %s in sources.lock.json\n' "$target" >&2; exit 2; }
    mkdir -p "$(dirname "$jaq")" "$root/.work/toolchain/$target/download"
    set -- $boot
    fetch "$root/.work/toolchain/$target/download/${1##*/}" "$1" "$2"
    cp "$root/.work/toolchain/$target/download/${1##*/}" "$jaq"
    chmod 755 "$jaq"
    printf '%s\n' "$2" > "$root/.work/toolchain/$target/jaq.sha256"
fi

install_input() {
    name=$1
    set -- $("$jaq" -r --arg n "$name" '.inputs[] | select(.name == $n) | "\(.tool) \(.url) \(.sha256)"' "$sources")
    tool=$1
    url=$2
    sha=$3
    file=$dest/download/${url##*/}
    mkdir -p "$dest/download"
    stamp=$dest/$tool.sha256
    if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$sha" ]; then return 0; fi
    if [ "$mode" = musl ]; then
        [ -f "$file" ] && [ "$(digest "$file")" = "$sha" ] || fetch "$file" "$url" "$sha"
    else
        "$dest/python/bin/python3.15" "$root/tools/fetch.py" "$sources" "$dest/download" "$name" >/dev/null
    fi
    if [ "$tool" != npm ]; then rm -rf "${dest:?}/$tool" && mkdir -p "$dest/$tool"; fi
    case $tool in
        node) tar -xf "$file" -C "$dest/$tool" --strip-components=1; rm -f "$dest/npm.sha256" ;;
        npm) rm -rf "$dest/node/lib/node_modules/npm" && mkdir -p "$dest/node/lib/node_modules/npm" && tar -xzf "$file" -C "$dest/node/lib/node_modules/npm" --strip-components=1 ;;
        python) tar -xzf "$file" -C "$dest/$tool" --strip-components=1 ;;
        jaq) cp "$file" "$dest/$tool/jaq" && chmod 755 "$dest/$tool/jaq" ;;
        *) printf 'unsupported toolchain input %s in sources.lock.json\n' "$name" >&2; exit 2 ;;
    esac
    printf '%s\n' "$sha" > "$stamp"
}

if [ "$mode" = musl ]; then
    names=$("$jaq" -r --arg t "$target" '.musl_check[$t] // empty' "$bootstrap")
    [ -n "$names" ] || { printf 'no musl check input for %s in bootstrap.lock.json\n' "$target" >&2; exit 2; }
    mkdir -p "$dest/bin" "$dest/download"
    for name in $names; do
        install_input "$name"
    done
    printf '%s\n' "$dest/node/bin"
    exit 0
fi

python_name=python-$target
python_sha=$("$jaq" -r --arg n "$python_name" '.inputs[] | select(.name == $n) | .sha256' "$sources")
[ -n "$python_sha" ] || { printf 'no %s input in sources.lock.json\n' "$python_name" >&2; exit 2; }
mkdir -p "$dest/bin" "$dest/download"
if [ ! -x "$dest/python/bin/python3.15" ] || [ "$(cat "$dest/python.sha256" 2>/dev/null)" != "$python_sha" ]; then
    python_url=$("$jaq" -r --arg n "$python_name" '.inputs[] | select(.name == $n) | .url' "$sources")
    python_file=$dest/download/${python_url##*/}
    fetch "$python_file" "$python_url" "$python_sha"
    rm -rf "$dest/python"
    mkdir -p "$dest/python"
    tar -xzf "$python_file" -C "$dest/python" --strip-components=1
    rm -f "$dest/npm.sha256"
    printf '%s\n' "$python_sha" > "$dest/python.sha256"
fi
py=$dest/python/bin/python3.15

wheel_url=$("$jaq" -r --arg n laputa-buildlib '.inputs[] | select(.name == $n) | .url' "$sources")
wheel_sha=$("$jaq" -r --arg n laputa-buildlib '.inputs[] | select(.name == $n) | .sha256' "$sources")
[ -n "$wheel_url" ] && [ -n "$wheel_sha" ] || { printf 'no laputa-buildlib input in sources.lock.json\n' >&2; exit 2; }
wheel=$dest/download/${wheel_url##*/}
fetch "$wheel" "$wheel_url" "$wheel_sha"
if [ "$(cat "$dest/buildlib.sha256" 2>/dev/null)" != "$wheel_sha" ] || ! "$py" -c 'import buildlib' 2>/dev/null; then
    # python-build-standalone strips ensurepip; the wheel is pinned by
    # sources.lock.json, so extracting it into the builder's site-packages is
    # as strong as a solver-based install for a dependency-free package
    "$py" - "$wheel" "$dest" <<'PY'
import shutil
import site
import sys
import zipfile
from pathlib import Path

wheel, dest = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
target = None
for candidate in site.getsitepackages():
    path = Path(candidate)
    if path.name == "site-packages" and path.resolve().is_relative_to(dest):
        target = path
if target is None:
    print(f"no site-packages directory inside {dest}", file=sys.stderr)
    raise SystemExit(2)
with zipfile.ZipFile(wheel) as bundle:
    for name in bundle.namelist():
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts:
            print(f"unsafe wheel member: {name}", file=sys.stderr)
            raise SystemExit(2)
    shutil.rmtree(target / "buildlib", ignore_errors=True)
    for stale in target.glob("laputa_buildlib-*.dist-info"):
        shutil.rmtree(stale)
    bundle.extractall(target)
PY
    printf '%s\n' "$wheel_sha" > "$dest/buildlib.sha256"
fi

names=$("$jaq" -r --arg t "$target" '(.targets[$t] // [])[]' "$bootstrap")
[ -n "$names" ] || { printf 'no toolchain pins for %s in bootstrap.lock.json\n' "$target" >&2; exit 2; }
for name in $names; do
    [ "$name" = "$python_name" ] && continue
    install_input "$name"
done

for tool in node python jaq; do
    [ -d "$dest/$tool" ] || [ -x "$dest/$tool/jaq" ] || continue
    for exe in "$dest/$tool"/bin/* "$dest/$tool"/jaq; do
        [ -e "$exe" ] && ln -sf "$exe" "$dest/bin/${exe##*/}"
    done
done
printf '%s\n' "$dest/bin"
[ -x "$dest/python/bin/python3.15" ] && printf '%s\n' "$dest/python/bin/python3.15"
exit 0
