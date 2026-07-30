#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
expected="87cc9d21c92c1cfd648e316e3e22e2961b644d375eec21c4ded1c0afc1de5a6e"

test -f "$root/components.lock.toml"
test -f "$root/live/profile.toml"
test -f "$root/branding/arach-logo.png"
test -f "$root/branding/source/arach-original.png"
printf '%s  %s\n' "$expected" "$root/branding/arach-logo.png" | sha256sum --check --strict
printf '%s  %s\n' "$expected" "$root/branding/source/arach-original.png" | sha256sum --check --strict

test "$(grep -c '^\[\[component\]\]' "$root/components.lock.toml")" -eq 11
grep -Fq 'repository = "https://github.com/SisyphusAeolides/Arach-Packages.git"' \
    "$root/components.lock.toml"
grep -Fq 'repository = "https://github.com/SisyphusAeolides/Arach-HWD.git"' \
    "$root/components.lock.toml"
python3 "$root/scripts/verify-components.py" --lock "$root/components.lock.toml"
python3 "$root/scripts/test_verify_components.py"
grep -Fxq 'session = "cosmic-session"' "$root/live/profile.toml"
grep -Fxq 'framework = "calamares"' "$root/live/profile.toml"
grep -Fxq 'allow_unmatched_binary_kernel_modules = false' "$root/live/profile.toml"

printf '%s\n' 'Arach OS foundation verified'
