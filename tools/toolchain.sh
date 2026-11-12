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

if [ "$mode" = musl ]; then
    names=$("$jaq" -r --arg t "$target" '.musl_check[$t] // empty' "$bootstrap")
else
    names=$("$jaq" -r --arg t "$target" '(.targets[$t] // [])[]' "$bootstrap")
fi
[ -n "$names" ] || { printf 'no toolchain pins for %s\n' "$target" >&2; exit 2; }
mkdir -p "$dest/bin" "$dest/download"

for name in $names; do
    set -- $("$jaq" -r --arg n "$name" '.inputs[] | select(.name == $n) | "\(.tool) \(.url) \(.sha256)"' "$sources")
    tool=$1
    url=$2
    sha=$3
    file=$dest/download/${url##*/}
    stamp=$dest/$tool.sha256
    if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$sha" ]; then continue; fi
    rm -f "$stamp"
    fetch "$file" "$url" "$sha"
    if [ "$tool" != npm ]; then rm -rf "${dest:?}/$tool" && mkdir -p "$dest/$tool"; fi
    case $tool in
        node) tar -xf "$file" -C "$dest/$tool" --strip-components=1; rm -f "$dest/npm.sha256" ;;
        npm) rm -rf "$dest/node/lib/node_modules/npm" && mkdir -p "$dest/node/lib/node_modules/npm" && tar -xzf "$file" -C "$dest/node/lib/node_modules/npm" --strip-components=1 ;;
        python) tar -xzf "$file" -C "$dest/$tool" --strip-components=1 ;;
        jaq) cp "$file" "$dest/$tool/jaq" && chmod 755 "$dest/$tool/jaq" ;;
    esac
    printf '%s\n' "$sha" > "$stamp"
done

if [ "$mode" = musl ]; then
    printf '%s\n' "$dest/node/bin"
    exit 0
fi
for tool in node python jaq; do
    [ -d "$dest/$tool" ] || continue
    for exe in "$dest/$tool"/bin/* "$dest/$tool"/jaq; do
        [ -e "$exe" ] && ln -sf "$exe" "$dest/bin/${exe##*/}"
    done
done
printf '%s\n' "$dest/bin"
[ -x "$dest/python/bin/python3.15" ] && printf '%s\n' "$dest/python/bin/python3.15"
exit 0
