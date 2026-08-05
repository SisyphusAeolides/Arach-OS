#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/arach-live-test.XXXXXX")
cleanup() { rm -rf -- "$tmp"; }
trap cleanup EXIT

boot_artifact_root=${ARACH_TEST_BOOT_ARTIFACT_ROOT:-}
preserved_iso=${ARACH_TEST_ISO_OUTPUT:-}
if [[ -n "$boot_artifact_root" ]]; then
    [[ "$boot_artifact_root" = /* && -d "$boot_artifact_root" && ! -L "$boot_artifact_root" ]] || {
        echo 'ARACH_TEST_BOOT_ARTIFACT_ROOT must be an absolute, real directory' >&2
        exit 64
    }
fi
if [[ -n "$preserved_iso" ]]; then
    [[ "$preserved_iso" = /* ]] || {
        echo 'ARACH_TEST_ISO_OUTPUT must be absolute' >&2
        exit 64
    }
    [[ ! -e "$preserved_iso" && ! -e "$preserved_iso.json" ]] || {
        echo 'ARACH_TEST_ISO_OUTPUT or its sidecar already exists' >&2
        exit 1
    }
fi

artifacts="$tmp/artifacts"
source="$tmp/source"
bundle_inputs="$tmp/bundle-inputs"
bundle="$tmp/boot-bundle"
generation="$tmp/system.gen"
output="$tmp/live-root"
mkdir -p "$artifacts" "$bundle_inputs"

mkdir -p "$artifacts/push-0.1.0-5/target/release"
printf '\177ELF test Push\n' > "$artifacts/push-0.1.0-5/target/release/push"
mkdir -p "$artifacts/corinth-0.1.0-9/target/x86_64-arach/release"
printf '\177ELF test Corinth\n' > "$artifacts/corinth-0.1.0-9/target/x86_64-arach/release/corinth"
mkdir -p "$artifacts/arach-hwd-0.1.0-1/target/release"
printf '\177ELF test Arach HWD\n' > "$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd"
printf '\177ELF test Arach HWD catalog sync\n' \
    > "$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd-catalog-sync"
printf '\177ELF test Arach HWD qualification\n' \
    > "$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd-qualify"
printf '\177ELF test Arach HWD evidence recorder\n' \
    > "$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd-record"
mkdir -p "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/profiles"
mkdir -p "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/driver-sources"
printf '[key]\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/keys.toml"
printf '1.0\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/driver-abi"
printf 'format = 1\nrepository = "arach-hardware"\nkey_id = "fixture"\n\n[[package]]\nname = "fixture-driver"\nversion = "1.0.0"\nrelease = 1\nscope = "driver"\nrepository = "arach-hardware"\nmetadata_sha256 = "%064d"\nartifact_sha256 = "%064d"\nsource_lock_sha256 = "%064d"\nurl = "https://packages.example.invalid/fixture.pkg"\nsize = 1\n' 0 1 2 > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/packages.toml"
printf 'key_id = "fixture"\nsignature = "fixture"\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/packages.toml.sig"
printf 'fixture profile\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/profiles/fixture.toml"
printf 'fixture signature\n' > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/profiles/fixture.toml.sig"
for source_name in modules.alias modules.dep modules.builtin modules.firmware modules.builtin.modinfo; do
    printf 'fixture %s\n' "$source_name" \
        > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/driver-sources/$source_name"
done
catalog_keyring_sha=$(sha256sum "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/keys.toml" | cut -d' ' -f1)
catalog_profile_sha=$(sha256sum "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/profiles/fixture.toml" | cut -d' ' -f1)
catalog_signature_sha=$(sha256sum "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/profiles/fixture.toml.sig" | cut -d' ' -f1)
catalog_driver_source_records=""
for source_name in modules.alias modules.dep modules.builtin modules.firmware modules.builtin.modinfo; do
    source_sha=$(sha256sum \
        "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/driver-sources/$source_name" \
        | cut -d' ' -f1)
    catalog_driver_source_records+=$'[[driver_source]]\n'
    catalog_driver_source_records+="path = \"driver-sources/$source_name\""$'\n'
    catalog_driver_source_records+="sha256 = \"$source_sha\""$'\n\n'
done
printf 'format = 1\nsnapshot = "test"\nkeyring_sha256 = "%s"\nrecipe_repository = "https://github.com/SisyphusAeolides/Arach-Packages.git"\nrecipe_revision = "054ca7af378ab33c48112603546653436aea7d56"\n\n[[profile]]\npath = "fixture.toml"\nprofile_sha256 = "%s"\nsignature_sha256 = "%s"\n' \
    "$catalog_keyring_sha" "$catalog_profile_sha" "$catalog_signature_sha" \
    > "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/catalog.lock"
printf '%s' "$catalog_driver_source_records" \
    >> "$artifacts/arach-hardware-catalog-2026.1/etc/arach/hwd/catalog.lock"
make_fake_elf() {
    local target="$1"
    local name="$2"
    if [[ -n "${ARACH_TEST_BOOT_ARTIFACT_ROOT:-}" ]]; then
        cp "$ARACH_TEST_BOOT_ARTIFACT_ROOT/crest" "$target"
        chmod +x "$target"
    else
        printf '\177ELF test %s\n' "$name" > "$target"
    fi
}

mkdir -p "$artifacts/dbus-broker-1/usr/bin"
make_fake_elf "$artifacts/dbus-broker-1/usr/bin/dbus-broker-launch" "D-Bus"
mkdir -p "$artifacts/seatd-0.9.3-1/usr/bin"
make_fake_elf "$artifacts/seatd-0.9.3-1/usr/bin/seatd" "seatd"
mkdir -p "$artifacts/pipewire-1.4.9-1/usr/bin"
make_fake_elf "$artifacts/pipewire-1.4.9-1/usr/bin/pipewire" "PipeWire"
make_fake_elf "$artifacts/pipewire-1.4.9-1/usr/bin/pipewire-pulse" "PipeWire Pulse"
mkdir -p "$artifacts/wireplumber-0.5.9-1/usr/bin"
make_fake_elf "$artifacts/wireplumber-0.5.9-1/usr/bin/wireplumber" "WirePlumber"
mkdir -p "$artifacts/greetd-0.10.3-1/target/release"
make_fake_elf "$artifacts/greetd-0.10.3-1/target/release/greetd" "greetd"
for binary in cosmic-comp cosmic-greeter cosmic-greeter-start cosmic-session cosmic-term xdg-desktop-portal-cosmic; do
    mkdir -p "$artifacts/cosmic-desktop-0.1.0-1/usr/bin"
    make_fake_elf "$artifacts/cosmic-desktop-0.1.0-1/usr/bin/$binary" "$binary"
done
mkdir -p "$artifacts/cosmic-desktop-0.1.0-1/etc/greetd"
printf '[default_session]\ncommand = "cosmic-greeter-start"\n' > "$artifacts/cosmic-desktop-0.1.0-1/etc/greetd/cosmic-greeter.toml"
mkdir -p "$artifacts/firefox-140.4.0esr-1/usr/bin"
make_fake_elf "$artifacts/firefox-140.4.0esr-1/usr/bin/firefox" "Firefox"
mkdir -p "$artifacts/calamares-3.4.2-1/usr/bin"
make_fake_elf "$artifacts/calamares-3.4.2-1/usr/bin/calamares" "Calamares"
installer_artifact="$artifacts/arach-os-0.1.0-1"
mkdir -p "$installer_artifact/target/release" "$installer_artifact/branding"
make_fake_elf "$installer_artifact/target/release/arach-install" "Installer"
printf 'PNG test branding\n' > "$installer_artifact/branding/arach-logo.png"
cp -a -- "$root/installer" "$installer_artifact/"

"$root/scripts/experimental-native-materialize-live-system.sh" "$artifacts" "$source"
if [[ -n "$boot_artifact_root" ]]; then
    for artifact in granite.efi arach push crest; do
        source_artifact="$boot_artifact_root/$artifact"
        [[ -f "$source_artifact" && ! -L "$source_artifact" ]] || {
            echo "measured boot test artifact is missing or symlinked: $source_artifact" >&2
            exit 1
        }
        cp -- "$source_artifact" "$bundle_inputs/$artifact"
    done
else
    printf 'MZ test Granite\n' > "$bundle_inputs/granite.efi"
    printf '\177ELF test Arach\n' > "$bundle_inputs/arach"
    printf '\177ELF test Push\n' > "$bundle_inputs/push"
    printf '\177ELF test Crest\n' > "$bundle_inputs/crest"
fi
for artifact in seatd dbus-broker pipewire wireplumber cosmic-comp cosmic-greeter cosmic-session xdg-desktop-portal-cosmic; do
    make_fake_elf "$bundle_inputs/$artifact" "$artifact"
done
"$root/scripts/experimental-native-assemble-boot-bundle.sh" "$bundle_inputs" "$bundle"
printf 'generation test\n' > "$generation"

"$root/scripts/experimental-native-assemble-live-root.sh" "$source" "$bundle" "$generation" "$output"
test -s "$output/run/arach-live/image.json"
test -s "$output/run/arach-live/system.json"
test -s "$output/run/arach-live/boot-bundle/manifest.json"
for artifact in seatd dbus-broker pipewire wireplumber cosmic-comp cosmic-greeter cosmic-session xdg-desktop-portal-cosmic; do
    test -s "$output/run/arach-live/boot-bundle/$artifact"
done
test -s "$output/run/arach-live/repository/system.gen"
test -s "$output/system/greetd"
test -s "$output/system/arach-hwd"
test -s "$output/system/arach-hwd-catalog-sync"
test -s "$output/system/arach-hwd-qualify"
test -s "$output/system/arach-hwd-record"
test -s "$output/etc/greetd/cosmic-greeter.toml"
test -s "$output/etc/greetd/config.toml"
test -s "$output/usr/bin/cosmic-greeter-start"
test -s "$output/etc/calamares/settings.conf"
test -s "$output/etc/calamares/modules/arach-hardware.conf"
test -s "$output/etc/calamares/modules/arach-pacman.conf"
test -s "$output/usr/lib/arach/calamares/modules/arachhardware/main.py"
test -s "$output/usr/lib/arach/calamares/modules/arachhardware/repository.py"
test -s "$output/usr/lib/arach/calamares/modules/arachpacman/adapter.py"
test -s "$output/usr/lib/arach/calamares/modules/arachpacman/schema.json"
test -s "$output/usr/lib/arach/calamares/modules/arachpacman/receipt-schema.json"
test -s "$output/usr/lib/arach/calamares/modules/arachtransaction/protocol.py"
test -s "$output/usr/share/calamares/branding/arach/branding.desc"
python3 - "$output/run/arach-live/image.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
assert manifest["schema"] == 1
assert manifest["distribution"] == "ArachOS"
assert manifest["composition"] == "native-stack"
assert manifest["release_role"] == "experimental"
assert manifest["entry_count"] > 10
assert len(manifest["root_sha256"]) == 64
PY
python3 - "$output/run/arach-live/boot-bundle/manifest.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    boot = json.load(stream)
for name in (
    "cosmic_seatd_sha256",
    "cosmic_dbus_sha256",
    "cosmic_pipewire_sha256",
    "cosmic_wireplumber_sha256",
    "cosmic_compositor_sha256",
    "cosmic_greeter_sha256",
    "cosmic_session_sha256",
    "cosmic_portal_sha256",
):
    assert len(boot[name]) == 64
PY
printf '%s\n' 'ArachOS live-root assembly verified'

bad_artifacts="$tmp/bad-artifacts"
cp -a -- "$artifacts" "$bad_artifacts"
rm -- "$bad_artifacts/push-0.1.0-5/target/release/push"
ln -s /etc/passwd -- "$bad_artifacts/push-0.1.0-5/target/release/push"
if "$root/scripts/experimental-native-materialize-live-system.sh" "$bad_artifacts" "$tmp/bad-root"; then
    echo 'materializer accepted a symlinked package output' >&2
    exit 1
fi
printf '%s\n' 'ArachOS materializer rejection gate verified'

missing_sync="$tmp/missing-sync-artifacts"
cp -a -- "$artifacts" "$missing_sync"
unlink "$missing_sync/arach-hwd-0.1.0-1/target/release/arach-hwd-catalog-sync"
if "$root/scripts/experimental-native-materialize-live-system.sh" "$missing_sync" "$tmp/missing-sync-root"; then
    echo 'materializer accepted an image without hardware catalog sync' >&2
    exit 1
fi
printf '%s\n' 'ArachOS hardware catalog sync presence gate verified'

missing_browser="$tmp/missing-browser-artifacts"
cp -a -- "$artifacts" "$missing_browser"
unlink "$missing_browser/firefox-140.4.0esr-1/usr/bin/firefox"
if "$root/scripts/experimental-native-materialize-live-system.sh" "$missing_browser" "$tmp/missing-browser-root"; then
    echo 'materializer accepted a live image without Firefox' >&2
    exit 1
fi
printf '%s\n' 'ArachOS browser presence gate verified'

image_tools=(xorriso mkfs.fat mcopy mksquashfs)
have_image_tools=true
for tool in "${image_tools[@]}"; do
    command -v "$tool" >/dev/null 2>&1 || have_image_tools=false
done
if "$have_image_tools"; then
    "$root/scripts/experimental-native-build-live-iso.sh" "$output" "$tmp/arach-os.iso"
    "$root/scripts/experimental-native-build-live-iso.sh" "$output" "$tmp/arach-os-repeat.iso"
    test -s "$tmp/arach-os.iso"
    test -s "$tmp/arach-os.iso.json"
    cmp --silent "$tmp/arach-os.iso" "$tmp/arach-os-repeat.iso"
    cmp --silent "$tmp/arach-os.iso.json" "$tmp/arach-os-repeat.iso.json"
    if [[ -n "$preserved_iso" ]]; then
        mkdir -p -- "$(dirname -- "$preserved_iso")"
        cp -- "$tmp/arach-os.iso" "$preserved_iso"
        cp -- "$tmp/arach-os.iso.json" "$preserved_iso.json"
        sync -f "$(dirname -- "$preserved_iso")"
    fi
    set +e
    "$root/scripts/experimental-native-build-live-iso.sh" >/dev/null 2>&1
    missing_args_status=$?
    set -e
    test "$missing_args_status" -eq 64
    xorriso -indev "$tmp/arach-os.iso" -report_el_torito plain 2>&1 \
        | grep -i -F 'efiboot.img' >/dev/null
    xorriso -osirrox on -indev "$tmp/arach-os.iso" \
        -extract /run/arach-live/rootfs.squashfs "$tmp/rootfs.squashfs" >/dev/null 2>&1
    test -s "$tmp/rootfs.squashfs"
    python3 - "$tmp/arach-os.iso.json" "$tmp/rootfs.squashfs" <<'PY'
import hashlib
import json
import pathlib
import sys

sidecar = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
rootfs = pathlib.Path(sys.argv[2])
hash_value = hashlib.sha256(rootfs.read_bytes()).hexdigest()
assert sidecar["rootfs_sha256"] == hash_value
assert sidecar["rootfs_size"] == rootfs.stat().st_size
assert sidecar["composition"] == "native-stack"
assert sidecar["release_role"] == "experimental"
PY
else
    set +e
    "$root/scripts/experimental-native-build-live-iso.sh" "$output" "$tmp/arach-os.iso"
    iso_status=$?
    set -e
    test "$iso_status" -eq 69
fi
printf '%s\n' 'ArachOS ISO tool gate verified'
