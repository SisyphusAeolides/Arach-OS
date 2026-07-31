#!/usr/bin/env bash
set -euo pipefail

# Assemble the exact input contract consumed by arach-install.  The source
# directory is a build output, never a live target root.  Every member is
# checked before it is copied and the destination is published in one rename.

if [[ $# -ne 2 ]]; then
    echo "usage: $0 SOURCE_DIR OUTPUT_DIR" >&2
    exit 64
fi

source_dir=$1
output_dir=$2
manifest_name=manifest.json

[[ "$source_dir" = /* && "$output_dir" = /* ]] || {
    echo "source and output directories must be absolute" >&2
    exit 64
}
[[ -d "$source_dir" && ! -L "$source_dir" ]] || {
    echo "source directory is not a real directory" >&2
    exit 1
}
[[ ! -e "$output_dir" ]] || {
    echo "output directory already exists; refusing replacement" >&2
    exit 1
}

max_bytes=$((32 * 1024 * 1024))
for artifact in granite.efi arach push crest; do
    path="$source_dir/$artifact"
    [[ -f "$path" && ! -L "$path" ]] || {
        echo "missing or non-regular boot artifact: $artifact" >&2
        exit 1
    }
    size=$(stat -c '%s' -- "$path")
    [[ "$size" -gt 0 && "$size" -le "$max_bytes" ]] || {
        echo "boot artifact has an invalid size: $artifact" >&2
        exit 1
    }
done

head -c 2 "$source_dir/granite.efi" | cmp -s - <(printf 'MZ') || {
    echo "Granite artifact is not PE/COFF" >&2
    exit 1
}
for artifact in arach push crest; do
    head -c 4 "$source_dir/$artifact" | cmp -s - <(printf '\177ELF') || {
        echo "ELF header missing from $artifact" >&2
        exit 1
    }
done

granite_sha=$(sha256sum "$source_dir/granite.efi" | awk '{print $1}')
arach_sha=$(sha256sum "$source_dir/arach" | awk '{print $1}')
push_sha=$(sha256sum "$source_dir/push" | awk '{print $1}')
crest_sha=$(sha256sum "$source_dir/crest" | awk '{print $1}')
for digest in "$granite_sha" "$arach_sha" "$push_sha" "$crest_sha"; do
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || {
        echo "sha256sum returned an invalid digest" >&2
        exit 1
    }
done

parent=$(dirname -- "$output_dir")
mkdir -p -- "$parent"
stage=$(mktemp -d "$parent/.boot-bundle.XXXXXX")
cleanup() {
    rm -rf -- "$stage"
}
trap cleanup EXIT
chmod 700 "$stage"
install -m 0644 -- "$source_dir/granite.efi" "$stage/granite.efi"
install -m 0644 -- "$source_dir/arach" "$stage/arach"
install -m 0644 -- "$source_dir/push" "$stage/push"
install -m 0644 -- "$source_dir/crest" "$stage/crest"
printf '{"arach_sha256":"%s","crest_sha256":"%s","granite_sha256":"%s","push_sha256":"%s","schema":1}\n' \
    "$arach_sha" "$crest_sha" "$granite_sha" "$push_sha" > "$stage/$manifest_name"
chmod 0644 "$stage/$manifest_name"
sync -f "$stage/$manifest_name"
mv -- "$stage" "$output_dir"
trap - EXIT
sync -f "$parent"

echo "assembled boot bundle: $output_dir"
