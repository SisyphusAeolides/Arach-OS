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

for marker in \
    "Granite: bounded Arach/Push/Crest preflight passed" \
    "ARACH_C0_RING3_SYSCALL_PASS" \
    "ARACH_C1_THREAD_FUTEX_PASS" \
    "ARACH_C1_ROBUST_FUTEX_PASS" \
    "ARACH_C1_SIGNAL_RETURN_PASS" \
    "ARACH_C2_FILE_MMAP_PASS" \
    "ARACH_C2_MPROTECT_PASS" \
    "ARACH_C1_PIPE_DESCRIPTOR_PASS" \
    "ARACH_C1_UNIX_SOCKET_PASS" \
    "ARACH_C1_SHARED_MEMORY_PASS" \
    "ARACH_C1_LINUX_SYSCALL_PASS" \
    "ARACH_C2_RUNTIME_LINKER_ENTER" \
    "ARACH_C2_DT_NEEDED_PASS" \
    "ARACH_C2_DEPENDENCY_GRAPH_PASS" \
    "ARACH_C2_MULTI_OBJECT_GRAPH_PASS" \
    "ARACH_C2_RUNPATH_PASS" \
    "ARACH_C2_SHARED_RELOCATION_PASS" \
    "ARACH_C2_PACKED_RELATIVE_PASS" \
    "ARACH_C2_COPY_RELOCATION_PASS" \
    "ARACH_C2_GLOBAL_SYMBOL_SCOPE_PASS" \
    "ARACH_C2_WEAK_BINDING_PASS" \
    "ARACH_C2_GLOBAL_DATA_PASS" \
    "ARACH_C2_ABSOLUTE_SYMBOL_PASS" \
    "ARACH_C2_SYMBOL_VERSION_PASS" \
    "ARACH_C2_STATIC_TLS_PASS" \
    "ARACH_C2_DYNAMIC_TLS_PASS" \
    "ARACH_C2_INITIALIZER_ORDER_PASS" \
    "ARACH_C2_EXTERNAL_SYMBOL_PASS" \
    "ARACH_C2_RUNTIME_LINKER_PASS" \
    "ARACH_C1_EXECVE_PASS" \
    "ARACH_C2_FINALIZATION_PASS" \
    "ARACH_C1_EXIT_GROUP_ARMED" \
    "[PID 1] child 2 exited with status 0" \
    "[PID 1] Kairos-dispatched workload complete" \
    "[PID 1] requesting 'seatd'" \
    "[PID 1] spawned service 9 as PID" \
    "[PID 1] requesting 'dbus-broker'" \
    "[PID 1] spawned service 4 as PID" \
    "[PID 1] requesting 'pipewire'" \
    "[PID 1] spawned service 10 as PID" \
    "[PID 1] requesting 'wireplumber'" \
    "[PID 1] spawned service 11 as PID" \
    "[PID 1] requesting 'cosmic-comp'" \
    "[PID 1] spawned service 5 as PID" \
    "[PID 1] requesting 'greetd (cosmic-greeter)'" \
    "[PID 1] spawned service 6 as PID"; do
    grep -F -- "$marker" "$log" >/dev/null || {
        echo "live ISO serial evidence missing: $marker" >&2
        exit 1
    }
done

previous_line=0
for marker in \
    "ARACH_C2_FILE_MMAP_PASS" \
    "ARACH_C2_MPROTECT_PASS" \
    "ARACH_C1_PIPE_DESCRIPTOR_PASS" \
    "ARACH_C1_UNIX_SOCKET_PASS" \
    "ARACH_C1_SHARED_MEMORY_PASS" \
    "ARACH_C1_LINUX_SYSCALL_PASS" \
    "ARACH_C2_RUNTIME_LINKER_ENTER" \
    "ARACH_C2_DT_NEEDED_PASS" \
    "ARACH_C2_DEPENDENCY_GRAPH_PASS" \
    "ARACH_C2_MULTI_OBJECT_GRAPH_PASS" \
    "ARACH_C2_RUNPATH_PASS" \
    "ARACH_C2_SHARED_RELOCATION_PASS" \
    "ARACH_C2_PACKED_RELATIVE_PASS" \
    "ARACH_C2_COPY_RELOCATION_PASS" \
    "ARACH_C2_GLOBAL_SYMBOL_SCOPE_PASS" \
    "ARACH_C2_WEAK_BINDING_PASS" \
    "ARACH_C2_GLOBAL_DATA_PASS" \
    "ARACH_C2_ABSOLUTE_SYMBOL_PASS" \
    "ARACH_C2_SYMBOL_VERSION_PASS" \
    "ARACH_C2_STATIC_TLS_PASS" \
    "ARACH_C2_DYNAMIC_TLS_PASS" \
    "ARACH_C2_INITIALIZER_ORDER_PASS" \
    "ARACH_C2_EXTERNAL_SYMBOL_PASS" \
    "ARACH_C2_RUNTIME_LINKER_PASS" \
    "ARACH_C1_EXECVE_PASS" \
    "ARACH_C2_FINALIZATION_PASS" \
    "ARACH_C1_EXIT_GROUP_ARMED" \
    "[PID 1] child 2 exited with status 0" \
    "[PID 1] Kairos-dispatched workload complete" \
    "[PID 1] requesting 'seatd'" \
    "[PID 1] spawned service 9 as PID" \
    "[PID 1] requesting 'dbus-broker'" \
    "[PID 1] spawned service 4 as PID" \
    "[PID 1] requesting 'pipewire'" \
    "[PID 1] spawned service 10 as PID" \
    "[PID 1] requesting 'wireplumber'" \
    "[PID 1] spawned service 11 as PID" \
    "[PID 1] requesting 'cosmic-comp'" \
    "[PID 1] spawned service 5 as PID" \
    "[PID 1] requesting 'greetd (cosmic-greeter)'" \
    "[PID 1] spawned service 6 as PID"; do
    line=$(grep -nF -m1 -- "$marker" "$log" | cut -d: -f1)
    if [[ "$line" -le "$previous_line" ]]; then
        echo "live ISO serial evidence is out of order: $marker" >&2
        exit 1
    fi
    previous_line=$line
done

if [[ "$status" -eq 124 ]]; then
    echo "live ISO execution gate passed before bounded QEMU timeout: $log"
else
    echo "live ISO execution gate passed: $log"
fi
