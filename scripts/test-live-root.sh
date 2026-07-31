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
mkdir -p "$artifacts/arach-hwd-0.1.0-1/target/release"
printf '\177ELF test Arach HWD\n' > "$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd"
mkdir -p "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/profiles"
printf '[key]\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/keys.toml"
printf '1.0\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/driver-abi"
catalog_keyring_sha=$(sha256sum "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/keys.toml" | cut -d' ' -f1)
printf 'format = 1\nsnapshot = "test"\nkeyring_sha256 = "%s"\n' "$catalog_keyring_sha" > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/catalog.lock"
mkdir -p "$artifacts/dbus-broker-1/usr/bin"
printf '\177ELF test D-Bus\n' > "$artifacts/dbus-broker-1/usr/bin/dbus-broker-launch"
mkdir -p "$artifacts/greetd-0.10.3-1/target/release"
printf '\177ELF test greetd\n' > "$artifacts/greetd-0.10.3-1/target/release/greetd"
for binary in cosmic-comp cosmic-greeter cosmic-greeter-start cosmic-session cosmic-term xdg-desktop-portal-cosmic; do
    mkdir -p "$artifacts/cosmic-desktop-0.1.0-1/usr/bin"
    printf '\177ELF test %s\n' "$binary" > "$artifacts/cosmic-desktop-0.1.0-1/usr/bin/$binary"
done
mkdir -p "$artifacts/cosmic-desktop-0.1.0-1/etc/greetd"
printf '[default_session]\ncommand = "cosmic-greeter-start"\n' > "$artifacts/cosmic-desktop-0.1.0-1/etc/greetd/cosmic-greeter.toml"
mkdir -p "$artifacts/firefox-140.4.0esr-1/usr/bin"
printf '\177ELF test Firefox\n' > "$artifacts/firefox-140.4.0esr-1/usr/bin/firefox"
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
test -s "$output/system/greetd"
test -s "$output/etc/greetd/cosmic-greeter.toml"
test -s "$output/etc/greetd/config.toml"
test -s "$output/usr/bin/cosmic-greeter-start"
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

missing_browser="$tmp/missing-browser-artifacts"
cp -a -- "$artifacts" "$missing_browser"
unlink "$missing_browser/firefox-140.4.0esr-1/usr/bin/firefox"
if "$root/scripts/materialize-live-system.sh" "$missing_browser" "$tmp/missing-browser-root"; then
    echo 'materializer accepted a live image without Firefox' >&2
    exit 1
fi
printf '%s\n' 'Arach OS browser presence gate verified'

if command -v xorriso >/dev/null 2>&1; then
    "$root/scripts/build-live-iso.sh" "$output" "$tmp/arach-os.iso"
    test -s "$tmp/arach-os.iso"
    test -s "$tmp/arach-os.iso.json"
    set +e
    "$root/scripts/build-live-iso.sh" >/dev/null 2>&1
    missing_args_status=$?
    set -e
    test "$missing_args_status" -eq 64
    xorriso -indev "$tmp/arach-os.iso" -report_el_torito plain 2>&1 \
        | grep -i -F 'efiboot.img' >/dev/null
else
    set +e
    "$root/scripts/build-live-iso.sh" "$output" "$tmp/arach-os.iso"
    iso_status=$?
    set -e
    test "$iso_status" -eq 69
fi
printf '%s\n' 'Arach OS ISO tool gate verified'
