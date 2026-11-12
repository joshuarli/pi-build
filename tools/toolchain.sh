#!/bin/sh
# Usage: sh tools/toolchain.sh TARGET
# Installs digest-verified builder tools under .work/toolchain/TARGET and
# prints their bin directory followed by the Python interpreter path.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
target=$1
dest=$root/.work/toolchain/$target
pins=$root/tools/toolchain.pins
grep -q "^$target " "$pins" || { printf 'no toolchain pins for %s\n' "$target" >&2; exit 2; }
mkdir -p "$dest/bin" "$dest/download"

digest() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

grep "^$target " "$pins" | while read -r _ tool url sha; do
    file=$dest/download/${url##*/}
    stamp=$dest/$tool.sha256
    if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$sha" ]; then continue; fi
    rm -f "$file" "$stamp"
    curl -fsSL --retry 3 -o "$file.part" "$url"
    actual=$(digest "$file.part")
    [ "$actual" = "$sha" ] || { printf '%s: sha256 %s, expected %s\n' "$url" "$actual" "$sha" >&2; rm -f "$file.part"; exit 1; }
    mv "$file.part" "$file"
    if [ "$tool" != npm ]; then rm -rf "${dest:?}/$tool" && mkdir -p "$dest/$tool"; fi
    case $tool in
        node) tar -xf "$file" -C "$dest/$tool" --strip-components=1; rm -f "$dest/npm.sha256" ;;
        npm) rm -rf "$dest/node/lib/node_modules/npm" && mkdir -p "$dest/node/lib/node_modules/npm" && tar -xzf "$file" -C "$dest/node/lib/node_modules/npm" --strip-components=1 ;;
        python) tar -xzf "$file" -C "$dest/$tool" --strip-components=1 ;;
        jaq) cp "$file" "$dest/$tool/jaq" && chmod 755 "$dest/$tool/jaq" ;;
    esac
    printf '%s\n' "$sha" > "$stamp"
done

for tool in node python jaq; do
    [ -d "$dest/$tool" ] || continue
    for exe in "$dest/$tool"/bin/* "$dest/$tool"/jaq; do
        [ -e "$exe" ] && ln -sf "$exe" "$dest/bin/${exe##*/}"
    done
done
printf '%s\n' "$dest/bin"
[ -x "$dest/python/bin/python3.15" ] && printf '%s\n' "$dest/python/bin/python3.15"
exit 0
