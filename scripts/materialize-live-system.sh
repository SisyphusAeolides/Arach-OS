#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 CORINTH_ARTIFACT_ROOT OUTPUT_ROOT" >&2
    exit 64
fi

artifact_root=$1
output_root=$2
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

for path in "$artifact_root" "$output_root"; do
    [[ "$path" = /* ]] || { echo "all paths must be absolute: $path" >&2; exit 64; }
done
[[ -d "$artifact_root" && ! -L "$artifact_root" ]] || {
    echo "Corinth artifact root is not a real directory" >&2
    exit 1
}
[[ ! -e "$output_root" ]] || {
    echo "output root already exists" >&2
    exit 1
}

parent=$(dirname -- "$output_root")
mkdir -p -- "$parent"
stage=$(mktemp -d "$parent/.arach-system.XXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT

python3 - "$repo_root/live/system.toml" "$artifact_root" "$stage" <<'PY'
import hashlib
import json
import os
import pathlib
import shutil
import stat
import sys
import tomllib

contract_path = pathlib.Path(sys.argv[1])
artifact_root = pathlib.Path(sys.argv[2])
stage = pathlib.Path(sys.argv[3])

with contract_path.open("rb") as stream:
    contract = tomllib.load(stream)

if contract.get("format") != 1 or contract.get("distribution") != "ArachOS":
    raise SystemExit("unsupported live system contract")
if contract.get("artifact_layout") != "corinth-v1":
    raise SystemExit("unsupported Corinth artifact layout")

providers = contract.get("provider", [])
for provider in providers:
    name = str(provider.get("name", ""))
    if "crest" in name.casefold():
        raise SystemExit(
            "Crest is reserved for the measured C0 boot payload and cannot be a live desktop provider"
        )
expected = {
    "push",
    "corinth",
    "arach-hwd",
    "arach-hardware-catalog",
    "dbus-broker",
    "seatd",
    "pipewire",
    "wireplumber",
    "greetd",
    "cosmic-desktop",
    "firefox",
    "calamares",
    "arach-install",
    "arach-branding",
}
if {p.get("name") for p in providers} != expected or len(providers) != len(expected):
    raise SystemExit("live system provider set differs from the contract")

def safe_relative(value):
    path = pathlib.PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts

def safe_absolute(value):
    path = pathlib.PurePosixPath(value)
    return path.is_absolute() and value != "/" and ".." not in path.parts

def real_regular(path, label):
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise SystemExit(f"missing {label}: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise SystemExit(f"{label} must be a regular non-symlink file: {path}")
    return info

def artifact_for(prefix):
    matches = []
    for entry in artifact_root.iterdir():
        info = entry.lstat()
        if entry.name.startswith(prefix) and stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
            matches.append(entry)
    if len(matches) != 1:
        raise SystemExit(f"expected one artifact directory for {prefix!r}, found {len(matches)}")
    return matches[0]

def ensure_no_symlink_parents(path, root):
    current = path
    while current != root:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise SystemExit(f"symlink path component is not allowed: {current}")
        current = current.parent

entries = {}
provider_records = []

def install_file(provider, source, destination, mode, source_root):
    if not safe_relative(source) or not safe_absolute(destination):
        raise SystemExit(f"unsafe mapping for {provider}: {source} -> {destination}")
    source_path = source_root / pathlib.PurePosixPath(source)
    ensure_no_symlink_parents(source_path, source_root)
    real_regular(source_path, f"{provider} source")
    target = stage / pathlib.PurePosixPath(destination.lstrip("/"))
    if target in entries or target.exists() or target.is_symlink():
        raise SystemExit(f"duplicate or unsafe live destination: {destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_parents(target.parent, stage)
    shutil.copyfile(source_path, target)
    os.chmod(target, mode)
    data = target.read_bytes()
    entries[target.relative_to(stage).as_posix()] = {
        "path": destination,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "mode": mode,
        "provider": provider,
    }

def install_alias(provider, source, destination, mode):
    if not safe_absolute(source) or not safe_absolute(destination):
        raise SystemExit(f"unsafe alias for {provider}: {source} -> {destination}")
    source_path = stage / pathlib.PurePosixPath(source.lstrip("/"))
    ensure_no_symlink_parents(source_path, stage)
    real_regular(source_path, f"{provider} alias source")
    target = stage / pathlib.PurePosixPath(destination.lstrip("/"))
    if target in entries or target.exists() or target.is_symlink():
        raise SystemExit(f"duplicate or unsafe live destination: {destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_parents(target.parent, stage)
    shutil.copyfile(source_path, target)
    os.chmod(target, mode)
    data = target.read_bytes()
    entries[target.relative_to(stage).as_posix()] = {
        "path": destination,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "mode": mode,
        "provider": provider,
    }

for provider in providers:
    name = provider["name"]
    prefix = provider["artifact_prefix"]
    layout = provider["layout"]
    if not provider.get("required") or not prefix.endswith("-"):
        raise SystemExit(f"invalid provider contract: {name}")
    artifact = artifact_for(prefix)
    files = provider.get("files", [])
    aliases = provider.get("aliases", [])
    required_tree = provider.get("required_tree_path", [])
    if layout == "tree":
        if files:
            raise SystemExit(f"tree provider has file mappings: {name}")
        for source_path in sorted(artifact.rglob("*")):
            info = source_path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise SystemExit(f"symlink in tree artifact {name}: {source_path}")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise SystemExit(f"unsupported tree entry {name}: {source_path}")
            relative = source_path.relative_to(artifact).as_posix()
            install_file(name, relative, "/" + relative, info.st_mode & 0o7777, artifact)
        for required in required_tree:
            if not safe_absolute(required):
                raise SystemExit(f"unsafe required tree path: {required}")
            target = stage / pathlib.PurePosixPath(required.lstrip("/"))
            if not target.is_file() or target.is_symlink():
                raise SystemExit(f"required tree artifact missing: {required}")
        if name == "arach-hardware-catalog":
            lock_path = artifact / "etc/arach/hwd/catalog.lock"
            profile_root = artifact / "etc/arach/hwd/profiles"
            try:
                with lock_path.open("rb") as stream:
                    catalog_lock = tomllib.load(stream)
            except (OSError, tomllib.TOMLDecodeError) as error:
                raise SystemExit(f"hardware catalog lock is unreadable: {error}")
            listed = catalog_lock.get("profile", [])
            if not isinstance(listed, list) or not listed:
                raise SystemExit("hardware catalog has no signed profiles")
            listed_paths = {entry.get("path") for entry in listed if isinstance(entry, dict)}
            actual_paths = {
                path.relative_to(profile_root).as_posix()
                for path in profile_root.rglob("*.toml")
                if path.is_file() and not path.is_symlink()
            }
            if listed_paths != actual_paths:
                raise SystemExit("hardware catalog lock does not enumerate its profiles")
            required_sources = {
                "driver-sources/modules.alias",
                "driver-sources/modules.dep",
                "driver-sources/modules.builtin",
                "driver-sources/modules.firmware",
                "driver-sources/modules.builtin.modinfo",
            }
            source_records = catalog_lock.get("driver_source", [])
            if not isinstance(source_records, list):
                raise SystemExit("hardware catalog driver source lock is invalid")
            source_paths = set()
            for record in source_records:
                if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                    raise SystemExit("hardware catalog driver source record is invalid")
                relative = record["path"]
                if (
                    not isinstance(relative, str)
                    or relative not in required_sources
                    or relative in source_paths
                    or len(record["sha256"]) != 64
                    or any(char not in "0123456789abcdef" for char in record["sha256"])
                ):
                    raise SystemExit("hardware catalog driver source record is invalid")
                source_paths.add(relative)
                source_path = artifact / "etc/arach/hwd" / pathlib.PurePosixPath(relative)
                real_regular(source_path, "hardware driver metadata")
                if hashlib.sha256(source_path.read_bytes()).hexdigest() != record["sha256"]:
                    raise SystemExit(f"hardware driver metadata digest differs from lock: {relative}")
            if source_paths != required_sources:
                raise SystemExit("hardware catalog lock does not enumerate the complete driver metadata snapshot")
        for alias in aliases:
            mode = alias.get("mode")
            if not isinstance(mode, int) or mode & ~0o7777:
                raise SystemExit(f"invalid alias mode for {name}")
            install_alias(name, alias["source"], alias["destination"], mode)
    elif layout == "files":
        if not files or aliases:
            raise SystemExit(f"file provider has no mappings: {name}")
        for file in files:
            mode = file.get("mode")
            if not isinstance(mode, int) or mode & ~0o7777:
                raise SystemExit(f"invalid mode for {name}")
            install_file(name, file["source"], file["destination"], mode, artifact)
    else:
        raise SystemExit(f"unsupported provider layout: {layout}")
    provider_records.append({"name": name, "artifact": artifact.name, "layout": layout})

stage_manifest = stage / "run/arach-live/system.json"
stage_manifest.parent.mkdir(parents=True, exist_ok=True)
ordered_entries = [entries[key] for key in sorted(entries)]
canonical = json.dumps(ordered_entries, separators=(",", ":"), sort_keys=True).encode()
manifest = {
    "schema": 1,
    "distribution": "ArachOS",
    "artifact_layout": "corinth-v1",
    "providers": provider_records,
    "entry_count": len(ordered_entries),
    "root_sha256": hashlib.sha256(canonical).hexdigest(),
    "entries": ordered_entries,
}
temporary = stage_manifest.with_name(".system.json.tmp")
temporary.write_text(json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
with temporary.open("rb") as stream:
    os.fsync(stream.fileno())
temporary.replace(stage_manifest)
PY

mv -- "$stage" "$output_root"
trap - EXIT
sync -f "$parent"
echo "materialized live system: $output_root"
sha256sum "$output_root/run/arach-live/system.json"
