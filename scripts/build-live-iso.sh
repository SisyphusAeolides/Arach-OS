#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 ASSEMBLED_LIVE_ROOT OUTPUT_ISO" >&2
    exit 64
fi

live_root=$1
output_iso=$2
xorriso_bin=${ARACH_XORRISO:-xorriso}
source_date_epoch=${SOURCE_DATE_EPOCH:-315532800}

if [[ ! "$source_date_epoch" =~ ^[0-9]+$ ]] \
    || ((${#source_date_epoch} > 10)) \
    || ((source_date_epoch < 315532800 || source_date_epoch > 4354819199)); then
    echo "SOURCE_DATE_EPOCH must fit the FAT timestamp range" >&2
    exit 64
fi
iso_date=$(date --utc --date="@$source_date_epoch" +%Y%m%d%H%M%S00)
[[ "$iso_date" =~ ^[0-9]{16}$ ]] || {
    echo "failed to derive the deterministic ISO date" >&2
    exit 1
}
export TZ=UTC

for path in "$live_root" "$output_iso"; do
    [[ "$path" = /* ]] || { echo "all paths must be absolute: $path" >&2; exit 64; }
done
[[ -d "$live_root" && ! -L "$live_root" ]] || {
    echo "assembled live root is not a real directory" >&2
    exit 1
}
[[ ! -e "$output_iso" ]] || {
    echo "output ISO already exists" >&2
    exit 1
}
command -v "$xorriso_bin" >/dev/null 2>&1 || {
    echo "xorriso is required to produce a bootable Arach ISO" >&2
    exit 69
}
for tool in mkfs.fat mcopy mksquashfs; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "$tool is required to produce the installable Arach ISO" >&2
        exit 69
    }
done

bundle="$live_root/run/arach-live/boot-bundle"
system_manifest="$live_root/run/arach-live/system.json"
image_manifest="$live_root/run/arach-live/image.json"
for path in \
    "$bundle/manifest.json" "$bundle/granite.efi" "$bundle/arach" \
    "$bundle/push" "$bundle/crest" "$system_manifest" "$image_manifest"; do
    [[ -f "$path" && ! -L "$path" ]] || {
        echo "live ISO input is missing or symlinked: $path" >&2
        exit 1
    }
done
for relative in \
    etc/calamares/settings.conf \
    etc/calamares/modules/arach-hardware.conf \
    etc/calamares/modules/arach-prepare.conf \
    etc/calamares/modules/arach-commit.conf \
    etc/calamares/modules/partition.conf \
    etc/calamares/modules/users.conf \
    etc/calamares/modules/unpackfs.conf \
    usr/lib/arach/calamares/modules/arachhardware/module.desc \
    usr/lib/arach/calamares/modules/arachhardware/main.py \
    usr/lib/arach/calamares/modules/arachhardware/repository.py \
    usr/lib/arach/calamares/modules/arachtransaction/module.desc \
    usr/lib/arach/calamares/modules/arachtransaction/main.py \
    usr/lib/arach/calamares/modules/arachtransaction/protocol.py \
    usr/share/calamares/branding/arach/branding.desc \
    usr/share/calamares/branding/arach/arach-logo.png; do
    path="$live_root/$relative"
    [[ -f "$path" && ! -L "$path" ]] || {
        echo "Calamares integration is missing or symlinked: /$relative" >&2
        exit 1
    }
done
cosmic_artifacts=(seatd dbus-broker pipewire wireplumber cosmic-comp cosmic-greeter cosmic-session xdg-desktop-portal-cosmic)
cosmic_count=0
for relative in "${cosmic_artifacts[@]}"; do
    if [[ -e "$bundle/$relative" ]]; then
        cosmic_count=$((cosmic_count + 1))
    fi
done
if [[ "$cosmic_count" -ne 0 && "$cosmic_count" -ne "${#cosmic_artifacts[@]}" ]]; then
    echo 'live ISO contains an incomplete native COSMIC service set' >&2
    exit 1
fi

parent=$(dirname -- "$output_iso")
mkdir -p -- "$parent"
work=$(mktemp -d "${TMPDIR:-/tmp}/arach-iso.XXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT

normalize_tree() {
    find "$1" -xdev -exec touch -h -d "@$source_date_epoch" -- {} +
}

stage="$work/root"
mkdir -p -- "$stage"
cp -a -- "$live_root/." "$stage/"

python3 - "$stage" <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
for path in root.rglob("*"):
    if not path.is_symlink():
        continue
    target = os.readlink(path)
    if os.path.isabs(target):
        raise SystemExit(f"absolute ISO-root symlink: {path}")
    resolved = (path.parent / target).resolve()
    if root not in resolved.parents and resolved != root:
        raise SystemExit(f"escaping ISO-root symlink: {path}")
    if path.is_dir():
        raise SystemExit(f"directory symlink is not allowed in ISO root: {path}")
PY

# Calamares installs this measured filesystem image. Keep live-only transaction
# inputs outside the installed root so the target cannot inherit stale plans,
# journals, or boot-bundle sources from the medium.
rootfs_source="$work/installed-root"
mkdir -p -- "$rootfs_source"
cp -a -- "$live_root/." "$rootfs_source/"
rm -rf -- "$rootfs_source/run/arach-live" "$rootfs_source/run/arach-installer"
normalize_tree "$rootfs_source"
mkdir -p -- "$stage/run/arach-live"
rootfs="$stage/run/arach-live/rootfs.squashfs"
mksquashfs "$rootfs_source" "$rootfs" \
    -noappend -all-root -comp zstd -no-progress -reproducible \
    -mkfs-time "$source_date_epoch" -all-time "$source_date_epoch" >/dev/null
[[ -s "$rootfs" ]] || {
    echo "mksquashfs produced an empty installer filesystem" >&2
    exit 1
}

mkdir -p -- "$stage/EFI/BOOT" "$stage/BOOT"
install -m 0644 -- "$bundle/granite.efi" "$stage/EFI/BOOT/BOOTX64.EFI"
install -m 0644 -- "$bundle/arach" "$stage/BOOT/ARACH"
install -m 0644 -- "$bundle/push" "$stage/BOOT/PUSH"
install -m 0644 -- "$bundle/crest" "$stage/BOOT/CREST"
if [[ "$cosmic_count" -eq "${#cosmic_artifacts[@]}" ]]; then
    install -m 0644 -- "$bundle/seatd" "$stage/BOOT/SEATD.BIN"
    install -m 0644 -- "$bundle/dbus-broker" "$stage/BOOT/DBUS.BIN"
    install -m 0644 -- "$bundle/pipewire" "$stage/BOOT/PIPEWIRE.BIN"
    install -m 0644 -- "$bundle/wireplumber" "$stage/BOOT/WIREPLUMBER.BIN"
    install -m 0644 -- "$bundle/cosmic-comp" "$stage/BOOT/COSCOMP.BIN"
    install -m 0644 -- "$bundle/cosmic-greeter" "$stage/BOOT/COSGREETER.BIN"
    install -m 0644 -- "$bundle/cosmic-session" "$stage/BOOT/COSSESSION.BIN"
    install -m 0644 -- "$bundle/xdg-desktop-portal-cosmic" "$stage/BOOT/COSPORTAL.BIN"
fi

# UEFI does not boot a raw PE file as an El Torito image. It boots a FAT EFI
# System Partition. Granite opens the filesystem that firmware used to load
# it, so the measured Arach/Push/C0 payloads must be present in that same FAT
# image rather than only in the surrounding ISO directory tree.
esp="$work/efiboot.img"
truncate -s $((128 * 1024 * 1024)) "$esp"
mkfs.fat --invariant -F 32 -i 00000000 -n ARACHEFI "$esp" >/dev/null
esp_root="$work/esp-root"
mkdir -p -- "$esp_root/EFI/BOOT" "$esp_root/BOOT"
install -m 0644 -- "$bundle/granite.efi" "$esp_root/EFI/BOOT/BOOTX64.EFI"
install -m 0644 -- "$bundle/manifest.json" "$esp_root/BOOT/MANIFEST.JSON"
install -m 0644 -- "$bundle/arach" "$esp_root/BOOT/ARACH"
install -m 0644 -- "$bundle/push" "$esp_root/BOOT/PUSH"
install -m 0644 -- "$bundle/crest" "$esp_root/BOOT/CREST"
if [[ "$cosmic_count" -eq "${#cosmic_artifacts[@]}" ]]; then
    install -m 0644 -- "$bundle/seatd" "$esp_root/BOOT/SEATD.BIN"
    install -m 0644 -- "$bundle/dbus-broker" "$esp_root/BOOT/DBUS.BIN"
    install -m 0644 -- "$bundle/pipewire" "$esp_root/BOOT/PIPEWIRE.BIN"
    install -m 0644 -- "$bundle/wireplumber" "$esp_root/BOOT/WIREPLUMBER.BIN"
    install -m 0644 -- "$bundle/cosmic-comp" "$esp_root/BOOT/COSCOMP.BIN"
    install -m 0644 -- "$bundle/cosmic-greeter" "$esp_root/BOOT/COSGREETER.BIN"
    install -m 0644 -- "$bundle/cosmic-session" "$esp_root/BOOT/COSSESSION.BIN"
    install -m 0644 -- "$bundle/xdg-desktop-portal-cosmic" "$esp_root/BOOT/COSPORTAL.BIN"
fi
normalize_tree "$esp_root"
mcopy -smp -i "$esp" "$esp_root"/* ::/
cp -- "$esp" "$stage/EFI/BOOT/efiboot.img"
normalize_tree "$stage"

temporary="$work/image.iso"
"$xorriso_bin" \
    -as mkisofs \
    -iso-level 3 \
    -full-iso9660-filenames \
    -J -joliet-long -R \
    -V ARACH_OS \
    --modification-date="$iso_date" \
    --set_all_file_dates "$iso_date" \
    -eltorito-alt-boot \
    -e EFI/BOOT/efiboot.img \
    -no-emul-boot \
    -o "$temporary" \
    "$stage"

[[ -s "$temporary" ]] || { echo "xorriso produced an empty ISO" >&2; exit 1; }
mv -- "$temporary" "$output_iso"
sync -f "$parent"

python3 - "$output_iso" "$image_manifest" "$system_manifest" "$bundle/manifest.json" "$rootfs" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

iso, image, system, boot, rootfs = map(pathlib.Path, sys.argv[1:])

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

record = {
    "schema": 1,
    "distribution": "Arach OS",
    "iso_sha256": digest(iso),
    "iso_size": iso.stat().st_size,
    "image_manifest_sha256": digest(image),
    "system_manifest_sha256": digest(system),
    "boot_bundle_manifest_sha256": digest(boot),
    "rootfs_sha256": digest(rootfs),
    "rootfs_size": rootfs.stat().st_size,
}
sidecar = iso.with_name(iso.name + ".json")
temporary = sidecar.with_name("." + sidecar.name + ".tmp")
temporary.write_text(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
with temporary.open("rb") as stream:
    os.fsync(stream.fileno())
temporary.replace(sidecar)
PY

echo "built Arach ISO: $output_iso"
sha256sum "$output_iso" "$output_iso.json"
