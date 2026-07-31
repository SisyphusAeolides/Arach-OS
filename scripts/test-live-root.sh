#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/arach-live-test.XXXXXX")
cleanup() { rm -rf -- "$tmp"; }
trap cleanup EXIT

source="$tmp/source"
bundle_inputs="$tmp/bundle-inputs"
bundle="$tmp/boot-bundle"
generation="$tmp/system.gen"
output="$tmp/live-root"
mkdir -p "$source" "$bundle_inputs"

for path in \
    system/push system/corinth system/slope-net system/crest \
    system/dbus-broker-launch system/cosmic-comp system/cosmic-greeter \
    system/cosmic-session system/xdg-desktop-portal-cosmic \
    usr/libexec/arach-install usr/bin/calamares \
    usr/share/calamares/branding/arach/arach-logo.png; do
    mkdir -p "$source/$(dirname "$path")"
    printf '\177ELF test artifact\n' > "$source/$path"
done
printf 'MZ test Granite\n' > "$bundle_inputs/granite.efi"
printf '\177ELF test Arach\n' > "$bundle_inputs/arach"
printf '\177ELF test Push\n' > "$bundle_inputs/push"
printf '\177ELF test Crest\n' > "$bundle_inputs/crest"
"$root/scripts/assemble-boot-bundle.sh" "$bundle_inputs" "$bundle"
printf 'generation test\n' > "$generation"

"$root/scripts/assemble-live-root.sh" "$source" "$bundle" "$generation" "$output"
test -s "$output/run/arach-live/image.json"
test -s "$output/run/arach-live/boot-bundle/manifest.json"
test -s "$output/run/arach-live/repository/system.gen"
python3 - "$output/run/arach-live/image.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
assert manifest["schema"] == 1
assert manifest["distribution"] == "Arach OS"
assert manifest["entry_count"] > 10
assert len(manifest["root_sha256"]) == 64
PY
printf '%s\n' 'Arach OS live-root assembly verified'
