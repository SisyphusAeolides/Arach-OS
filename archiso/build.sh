#!/usr/bin/env bash
set -euo pipefail

readonly profile_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly project_root="$(cd -- "${profile_root}/.." && pwd)"
readonly source_modules="${profile_root}/../installer/calamares/modules"
readonly catalog_root="${ARACH_HWD_CATALOG_ROOT:?set ARACH_HWD_CATALOG_ROOT to a signed catalog directory}"
readonly snapshot_root="${ARACH_HWD_PACMAN_SNAPSHOT_ROOT:?set ARACH_HWD_PACMAN_SNAPSHOT_ROOT to a signed Pacman snapshot directory}"
readonly output_root="${ARACHOS_ISO_OUTPUT:?set ARACHOS_ISO_OUTPUT to the output directory}"
: "${ARACHOS_ISO_VERSION:?set ARACHOS_ISO_VERSION to an immutable release version}"

require_regular() {
    [[ -f "$1" && ! -L "$1" ]] || {
        printf 'missing required regular file: %s\n' "$1" >&2
        exit 1
    }
}

require_directory() {
    [[ -d "$1" && ! -L "$1" ]] || {
        printf 'missing required directory: %s\n' "$1" >&2
        exit 1
    }
}

require_directory "$catalog_root"
for file in keys.toml catalog.lock packages.toml packages.toml.sig driver-abi; do
    require_regular "${catalog_root}/${file}"
done
require_directory "${catalog_root}/profiles"
require_directory "${catalog_root}/driver-sources"
require_directory "$snapshot_root"
for file in pacman-snapshot.toml pacman-snapshot.toml.sig pacman-snapshot.gpg pacman.conf; do
    require_regular "${snapshot_root}/${file}"
done
require_directory "${snapshot_root}/packages"

build_root="$(mktemp -d -- "${project_root}/.archiso-build.XXXXXX")"
trap 'rm -rf -- "$build_root"' EXIT
profile="${build_root}/profile"
cp -a -- "$profile_root" "$profile"

install -d \
    "${profile}/airootfs/etc/calamares/modules" \
    "${profile}/airootfs/usr/lib/calamares/modules" \
    "${profile}/airootfs/etc/arach/hwd"
install -m 0644 "${profile}/calamares/settings.conf" \
    "${profile}/airootfs/etc/calamares/settings.conf"
install -m 0644 "${profile}/calamares/modules/"*.conf \
    "${profile}/airootfs/etc/calamares/modules/"
cp -a -- \
    "${source_modules}/arachhardware" \
    "${source_modules}/arachpacman" \
    "${profile}/airootfs/usr/lib/calamares/modules/"
cp -a -- "${catalog_root}/." "${profile}/airootfs/etc/arach/hwd/"
install -m 0644 "${snapshot_root}/pacman-snapshot.toml" \
    "${profile}/airootfs/etc/arach/hwd/pacman-snapshot.toml"
install -m 0644 "${snapshot_root}/pacman-snapshot.toml.sig" \
    "${profile}/airootfs/etc/arach/hwd/pacman-snapshot.toml.sig"
install -m 0644 "${snapshot_root}/pacman-snapshot.gpg" \
    "${profile}/airootfs/etc/arach/hwd/pacman-snapshot.gpg"
install -d "${profile}/airootfs/etc/arach/hwd/pacman-snapshot"
install -m 0644 "${snapshot_root}/pacman.conf" \
    "${profile}/airootfs/etc/arach/hwd/pacman-snapshot/pacman.conf"
cp -a -- "${snapshot_root}/packages/." \
    "${profile}/airootfs/etc/arach/hwd/pacman-snapshot/"

mkdir -p -- "$output_root"
mkarchiso -v -w "${build_root}/work" -o "$output_root" "$profile"
