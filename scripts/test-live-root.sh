#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/arach-live-test.XXXXXX")
cleanup() { rm -rf -- "$tmp"; }
trap cleanup EXIT

artifacts="$tmp/artifacts"
source="$tmp/source"
bundle_inputs="$tmp/bundle-inputs"
bundle="$tmp/boot-bundle"
generation="$tmp/system.gen"
output="$tmp/live-root"
mkdir -p "$artifacts" "$bundle_inputs"

mkdir -p "$artifacts/push-0.1.0-5/target/release"
printf '\177ELF test Push\n' > "$artifacts/push-0.1.0-5/target/release/push"
mkdir -p "$artifacts/corinth-0.1.0-9/target/release"
printf '\177ELF test Corinth\n' > "$artifacts/corinth-0.1.0-9/target/release/corinth"
mkdir -p "$artifacts/dbus-broker-1/usr/bin"
printf '\177ELF test D-Bus\n' > "$artifacts/dbus-broker-1/usr/bin/dbus-broker-launch"
for binary in cosmic-comp cosmic-greeter cosmic-session xdg-desktop-portal-cosmic; do
    mkdir -p "$artifacts/cosmic-desktop-0.1.0-1/usr/bin"
    printf '\177ELF test %s\n' "$binary" > "$artifacts/cosmic-desktop-0.1.0-1/usr/bin/$binary"
done
mkdir -p "$artifacts/calamares-3.4.2-1/usr/bin"
printf '\177ELF test Calamares\n' > "$artifacts/calamares-3.4.2-1/usr/bin/calamares"
mkdir -p "$artifacts/arach-os-0.1.0-1/target/release" "$artifacts/arach-os-0.1.0-1/branding"
printf '\177ELF test Installer\n' > "$artifacts/arach-os-0.1.0-1/target/release/arach-install"
printf 'PNG test branding\n' > "$artifacts/arach-os-0.1.0-1/branding/arach-logo.png"

"$root/scripts/materialize-live-system.sh" "$artifacts" "$source"
printf 'MZ test Granite\n' > "$bundle_inputs/granite.efi"
printf '\177ELF test Arach\n' > "$bundle_inputs/arach"
printf '\177ELF test Push\n' > "$bundle_inputs/push"
printf '\177ELF test Crest\n' > "$bundle_inputs/crest"
"$root/scripts/assemble-boot-bundle.sh" "$bundle_inputs" "$bundle"
printf 'generation test\n' > "$generation"

"$root/scripts/assemble-live-root.sh" "$source" "$bundle" "$generation" "$output"
test -s "$output/run/arach-live/image.json"
test -s "$output/run/arach-live/system.json"
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

bad_artifacts="$tmp/bad-artifacts"
cp -a -- "$artifacts" "$bad_artifacts"
rm -- "$bad_artifacts/push-0.1.0-5/target/release/push"
ln -s /etc/passwd -- "$bad_artifacts/push-0.1.0-5/target/release/push"
if "$root/scripts/materialize-live-system.sh" "$bad_artifacts" "$tmp/bad-root"; then
    echo 'materializer accepted a symlinked package output' >&2
    exit 1
fi
printf '%s\n' 'Arach OS materializer rejection gate verified'

if command -v xorriso >/dev/null 2>&1; then
    "$root/scripts/build-live-iso.sh" "$output" "$tmp/arach-os.iso"
    test -s "$tmp/arach-os.iso"
    test -s "$tmp/arach-os.iso.json"
else
    set +e
    "$root/scripts/build-live-iso.sh" "$output" "$tmp/arach-os.iso"
    iso_status=$?
    set -e
    test "$iso_status" -eq 69
fi
printf '%s\n' 'Arach OS ISO tool gate verified'
