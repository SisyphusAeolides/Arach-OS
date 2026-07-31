#!/usr/bin/env bash
set -euo pipefail

# Assemble the POSIX root consumed by the Arach live medium. This stage is
# deliberately separate from ISO creation: an ISO writer may vary, while the
# root layout, measured boot inputs, and manifest must remain identical.
if [[ $# -ne 4 ]]; then
    echo "usage: $0 SOURCE_ROOT BOOT_BUNDLE SYSTEM_GENERATION OUTPUT_ROOT" >&2
    exit 64
fi

source_root=$1
boot_bundle=$2
generation=$3
output_root=$4
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

for path in "$source_root" "$boot_bundle" "$generation" "$output_root"; do
    [[ "$path" = /* ]] || { echo "all paths must be absolute: $path" >&2; exit 64; }
done
[[ -d "$source_root" && ! -L "$source_root" ]] || { echo "source root is not a real directory" >&2; exit 1; }
[[ -d "$boot_bundle" && ! -L "$boot_bundle" ]] || { echo "boot bundle is not a real directory" >&2; exit 1; }
[[ -f "$generation" && ! -L "$generation" ]] || { echo "generation is not a regular file" >&2; exit 1; }
[[ ! -e "$output_root" ]] || { echo "output root already exists" >&2; exit 1; }

mapfile -t required_paths < <(python3 - "$repo_root/live/image.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as stream:
    image = tomllib.load(stream)
if image.get("format") != 1 or image.get("distribution") != "Arach OS":
    raise SystemExit("unsupported live image contract")
if image.get("root_layout") != "posix":
    raise SystemExit("unsupported live root layout")
if image.get("boot_bundle_source") != "/run/arach-live/boot-bundle":
    raise SystemExit("boot bundle source differs from the installer contract")
if image.get("repository_generation") != "/run/arach-live/repository/system.gen":
    raise SystemExit("repository generation differs from the installer contract")
if image.get("manifest") != "/run/arach-live/image.json":
    raise SystemExit("live manifest differs from the image contract")
for value in image.get("required_path", []):
    if not value.startswith("/") or "/../" in value or value.endswith("/.."):
        raise SystemExit(f"unsafe required path: {value}")
    print(value)
PY
)
(( ${#required_paths[@]} > 0 )) || { echo "live image contract has no required paths" >&2; exit 1; }

for relative in manifest.json granite.efi arach push crest; do
    path="$boot_bundle/$relative"
    [[ -f "$path" && ! -L "$path" ]] || { echo "boot bundle member missing: $relative" >&2; exit 1; }
done

parent=$(dirname -- "$output_root")
mkdir -p -- "$parent"
stage=$(mktemp -d "$parent/.arach-live-root.XXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT

# The source root may contain ordinary POSIX symlinks (for example /bin), so
# preserve them. Reserved measured paths are installed after this copy and are
# checked independently below.
cp -a -- "$source_root/." "$stage/"
mkdir -p -- "$stage/run/arach-live/boot-bundle" "$stage/run/arach-live/repository"
for relative in manifest.json granite.efi arach push crest; do
    cp -a -- "$boot_bundle/$relative" "$stage/run/arach-live/boot-bundle/$relative"
done
cp -a -- "$generation" "$stage/run/arach-live/repository/system.gen"

# Keep the image contract visible inside the live system, independent of the
# build checkout that produced it.
mkdir -p -- "$stage/usr/share/arach-os"
cp -- "$repo_root/live/profile.toml" "$stage/usr/share/arach-os/live-profile.toml"
cp -- "$repo_root/live/image.toml" "$stage/usr/share/arach-os/live-image.toml"
cp -- "$repo_root/installer/contract.toml" "$stage/usr/share/arach-os/installer-contract.toml"

for absolute in "${required_paths[@]}"; do
    path="$stage$absolute"
    [[ -f "$path" && ! -L "$path" ]] || {
        echo "required live artifact missing or symlinked: $absolute" >&2
        exit 1
    }
done

python3 - "$stage" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
manifest = stage / "run/arach-live/image.json"
entries = []
for path in sorted(stage.rglob("*")):
    relative = path.relative_to(stage).as_posix()
    if relative == "run/arach-live/image.json":
        continue
    if path.is_symlink():
        target = os.readlink(path)
        if os.path.isabs(target):
            raise SystemExit(f"absolute live-root symlink: {relative}")
        resolved = (path.parent / target).resolve()
        if stage not in resolved.parents and resolved != stage:
            raise SystemExit(f"escaping live-root symlink: {relative}")
        entries.append({"path": relative, "type": "symlink", "target": target})
    elif path.is_file():
        data = path.read_bytes()
        entries.append({
            "path": relative,
            "type": "file",
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    elif not path.is_dir():
        raise SystemExit(f"unsupported live-root entry: {relative}")

canonical = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
boot_manifest = next(
    entry["sha256"] for entry in entries
    if entry["path"] == "run/arach-live/boot-bundle/manifest.json"
)
generation = next(
    entry["sha256"] for entry in entries
    if entry["path"] == "run/arach-live/repository/system.gen"
)
image = {
    "schema": 1,
    "distribution": "Arach OS",
    "root_layout": "posix",
    "boot_bundle_manifest": boot_manifest,
    "repository_generation": generation,
    "entry_count": len(entries),
    "root_sha256": hashlib.sha256(canonical).hexdigest(),
    "entries": entries,
}
manifest.parent.mkdir(parents=True, exist_ok=True)
temporary = manifest.with_name(".image.json.tmp")
temporary.write_text(
    json.dumps(image, separators=(",", ":"), sort_keys=True) + "\n",
    encoding="utf-8",
)
with temporary.open("rb") as stream:
    os.fsync(stream.fileno())
temporary.replace(manifest)
PY

mv -- "$stage" "$output_root"
trap - EXIT
sync -f "$parent"
echo "assembled live root: $output_root"
sha256sum "$output_root/run/arach-live/image.json"
