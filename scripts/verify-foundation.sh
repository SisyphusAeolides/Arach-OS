#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
expected="87cc9d21c92c1cfd648e316e3e22e2961b644d375eec21c4ded1c0afc1de5a6e"

test -f "$root/components.lock.toml"
test -f "$root/live/profile.toml"
test -f "$root/live/image.toml"
test -f "$root/live/system.toml"
test -x "$root/scripts/assemble-live-root.sh"
test -x "$root/scripts/materialize-live-system.sh"
test -x "$root/scripts/build-live-iso.sh"
test -x "$root/scripts/test-live-root.sh"
test -f "$root/branding/arach-logo.png"
test -f "$root/branding/source/arach-original.png"
test -f "$root/installer/contract.toml"
test -f "$root/installer/calamares/settings.conf"
test -f "$root/installer/calamares/modules/arachtransaction/main.py"
printf '%s  %s\n' "$expected" "$root/branding/arach-logo.png" | sha256sum --check --strict
printf '%s  %s\n' "$expected" "$root/branding/source/arach-original.png" | sha256sum --check --strict

test "$(grep -c '^\[\[component\]\]' "$root/components.lock.toml")" -eq 11
grep -Fq 'repository = "https://github.com/SisyphusAeolides/Arach-Packages.git"' \
    "$root/components.lock.toml"
grep -Fq 'repository = "https://github.com/SisyphusAeolides/Arach-HWD.git"' \
    "$root/components.lock.toml"
python3 "$root/scripts/verify-components.py" \
    --lock "$root/components.lock.toml" \
    --manifest "$root/Cargo.toml"
python3 "$root/scripts/test_verify_components.py"
python3 "$root/installer/calamares/modules/arachtransaction/test_protocol.py"
grep -Fxq 'session = "cosmic-session"' "$root/live/profile.toml"
grep -Fxq 'framework = "calamares"' "$root/live/profile.toml"
grep -Fxq 'allow_unmatched_binary_kernel_modules = false' "$root/live/profile.toml"
grep -Fq '/etc/arach/hwd/driver-sources/modules.alias' \
    "$root/installer/calamares/modules/arachhardware.conf"
grep -Fq '/etc/arach/hwd/driver-sources/modules.firmware' \
    "$root/installer/calamares/modules/arachhardware.conf"

"$root/scripts/test-live-root.sh"

printf '%s\n' 'Arach OS foundation verified'
