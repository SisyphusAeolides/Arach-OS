#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 LIVE_ISO [SERIAL_LOG]" >&2
    exit 64
fi

image=$1
log=${2:-${image}.serial.log}
qemu=${QEMU:-qemu-system-x86_64}

for path in "$image" "$log"; do
    [[ "$path" = /* ]] || { echo "all paths must be absolute: $path" >&2; exit 64; }
done
[[ -f "$image" && ! -L "$image" ]] || {
    echo "live ISO is not a regular file" >&2
    exit 1
}
command -v "$qemu" >/dev/null || {
    echo "QEMU is required for live ISO execution" >&2
    exit 69
}

first_existing() {
    local candidate
    for candidate in "$@"; do
        if [[ -f "$candidate" && ! -L "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

ovmf_code=${OVMF_CODE:-}
ovmf_vars=${OVMF_VARS:-}
if [[ -z "$ovmf_code" ]]; then
    ovmf_code=$(first_existing \
        /usr/share/OVMF/OVMF_CODE_4M.fd \
        /usr/share/OVMF/OVMF_CODE.fd \
        /usr/share/edk2/ovmf/OVMF_CODE_4M.fd \
        /usr/share/edk2/ovmf/OVMF_CODE.fd) || true
fi
if [[ -z "$ovmf_vars" ]]; then
    ovmf_vars=$(first_existing \
        /usr/share/OVMF/OVMF_VARS_4M.fd \
        /usr/share/OVMF/OVMF_VARS.fd \
        /usr/share/edk2/ovmf/OVMF_VARS_4M.fd \
        /usr/share/edk2/ovmf/OVMF_VARS.fd) || true
fi
[[ -n "$ovmf_code" && -n "$ovmf_vars" \
    && -f "$ovmf_code" && ! -L "$ovmf_code" \
    && -f "$ovmf_vars" && ! -L "$ovmf_vars" ]] || {
    echo "OVMF_CODE and OVMF_VARS are required for live ISO execution" >&2
    exit 69
}

vars=$(mktemp /tmp/arach-live-vars.XXXXXX)
cleanup() { rm -f -- "$vars"; }
trap cleanup EXIT
cp -- "$ovmf_vars" "$vars"

mkdir -p -- "$(dirname -- "$log")"
: >"$log"
timeout_seconds=${ARACH_LIVE_TIMEOUT_SECONDS:-120}
set +e
timeout --kill-after=5s "${timeout_seconds}s" "$qemu" \
    -machine q35 \
    -m 1024M \
    -display none \
    -no-reboot \
    -no-shutdown \
    -boot order=d,strict=on \
    -serial "file:$log" \
    -drive "if=pflash,format=raw,readonly=on,file=$ovmf_code" \
    -drive "if=pflash,format=raw,file=$vars" \
    -drive "if=none,id=arach-cd,format=raw,readonly=on,file=$image" \
    -device ide-cd,drive=arach-cd
status=$?
set -e
if [[ "$status" -ne 0 && "$status" -ne 124 ]]; then
    echo "live ISO QEMU exited with status $status" >&2
    exit "$status"
fi

require_marker() {
    local marker=$1
    if ! grep -Eq -- "$marker" "$log" >/dev/null; then
        echo "live ISO serial evidence missing: $marker" >&2
        exit 1
    fi
}

first_line() {
    grep -nE -m1 -- "$1" "$log" | cut -d: -f1
}

tsv_escape() {
    local value=$1
    printf '%s' "$value" | sed -e 's/\\/\\\\/g' -e 's/\t/\\t/g' -e 's/\r/\\r/g'
}

collect_markers() {
    local src=$1
    local -n out=$2
    local -n seen=$3
    while IFS= read -r marker; do
        marker=${marker//$'\r'/}
        marker=${marker#"${marker%%[![:space:]]*}"}
        marker=${marker%"${marker##*[![:space:]]}"}
        if [[ -z "$marker" ]] || [[ "$marker" == \#* ]]; then
            continue
        fi
        if [[ -z "${seen[$marker]:-}" ]]; then
            seen[$marker]=1
            out+=("$marker")
        fi
    done < <(printf '%s\n' "$src")
}

collect_markers_file() {
    local path=$1
    local -n out=$2
    local -n seen=$3

    if [[ ! -f "$path" ]]; then
        echo "Marker source file not found: $path" >&2
        exit 1
    fi

    while IFS= read -r marker; do
        marker=${marker//$'\r'/}
        marker=${marker#"${marker%%[![:space:]]*}"}
        marker=${marker%"${marker##*[![:space:]]}"}
        if [[ -z "$marker" ]] || [[ "$marker" == \#* ]]; then
            continue
        fi
        if [[ -z "${seen[$marker]:-}" ]]; then
            seen[$marker]=1
            out+=("$marker")
        fi
    done < "$path"
}

require_marker "Granite: bounded Arach/Push/Crest preflight passed"
require_marker "\\[PID 1\\] Kairos-dispatched workload complete"

if grep -Eq "\\[PID 1\\] requesting 'seatd'" "$log"; then
    service_request_marker="\\[PID 1\\] requesting 'seatd'"
    service_spawn_marker="\\[PID 1\\] spawned service (Seatd|[0-9]+) as PID"
else
    if ! grep -Eq "\\[PID 1\\] requesting 'crest'" "$log"; then
        echo "live ISO serial evidence missing: service startup request marker" >&2
        exit 1
    fi
    service_request_marker="\\[PID 1\\] requesting 'crest'"
    service_spawn_marker="\\[PID 1\\] spawned service (Crest|[0-9]+) as PID"
fi

require_marker "$service_request_marker"
require_marker "$service_spawn_marker"
require_marker "ARACH_C0_RING3_SYSCALL_PASS"

session_markers=()
declare -A session_markers_seen
if [[ -n "${ARACH_LIVE_SESSION_MARKERS_FILE:-}" ]]; then
    collect_markers_file "$ARACH_LIVE_SESSION_MARKERS_FILE" session_markers session_markers_seen
fi

if [[ -n "${ARACH_LIVE_SESSION_MARKERS:-}" ]]; then
    collect_markers "$ARACH_LIVE_SESSION_MARKERS" session_markers session_markers_seen
fi

cosmic_lifecycle_markers=()
declare -A cosmic_lifecycle_markers_seen
if [[ -n "${ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS_FILE:-}" ]]; then
    collect_markers_file "$ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS_FILE" cosmic_lifecycle_markers cosmic_lifecycle_markers_seen
fi

if [[ -n "${ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS:-}" ]]; then
    collect_markers "$ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS" cosmic_lifecycle_markers cosmic_lifecycle_markers_seen
fi

previous_line=0
checked_marker_lines=()
checked_markers=()
for marker in \
    "Granite: bounded Arach/Push/Crest preflight passed" \
    "\\[PID 1\\] Kairos-dispatched workload complete" \
    "$service_request_marker" \
    "$service_spawn_marker" \
    "ARACH_C0_RING3_SYSCALL_PASS" \
    "${session_markers[@]}" \
    "${cosmic_lifecycle_markers[@]}"; do
    if [[ -z "$marker" ]]; then
        continue
    fi
    require_marker "$marker"
    line=$(first_line "$marker")
    if [[ "$line" -le "$previous_line" ]]; then
        echo "live ISO serial evidence is out of order: $marker" >&2
        exit 1
    fi
    previous_line=$line
    checked_markers+=("$marker")
    checked_marker_lines+=("$line")
done

if [[ -n "${ARACH_LIVE_MARKER_REPORT:-}" ]]; then
    {
        echo -e "marker\tline_number"
        for i in "${!checked_markers[@]}"; do
            echo -e "$(tsv_escape "${checked_markers[$i]}")\t${checked_marker_lines[$i]}"
        done
    } >"${ARACH_LIVE_MARKER_REPORT}"
fi

if [[ "$status" -eq 124 ]]; then
    echo "live ISO execution gate passed before bounded QEMU timeout: $log"
else
    echo "live ISO execution gate passed: $log"
fi
