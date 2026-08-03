#!/usr/bin/env python3
from pathlib import Path

CORINTH = "afa2373b5be11bd53e6b697ba4c7d96ee8fce028"
PACKAGES = "7a93a7a78e99555234f8c69dceb8ee418ea6ab1b"

cargo = Path("Cargo.toml")
text = cargo.read_text(encoding="utf-8")
old = 'corinth = { git = "https://github.com/SisyphusAeolides/Corinth.git", rev = "015c734ecfed3c78760545a5e598f672807349b1", features = ["host-store"] }'
new = f'corinth = {{ git = "https://github.com/SisyphusAeolides/Corinth.git", rev = "{CORINTH}", features = ["host-store"] }}'
if text.count(old) != 1:
    raise SystemExit("Cargo.toml Corinth pin differs")
cargo.write_text(text.replace(old, new), encoding="utf-8")

lock = Path("components.lock.toml")
text = lock.read_text(encoding="utf-8")
replacements = {
    'revision = "015c734ecfed3c78760545a5e598f672807349b1"': f'revision = "{CORINTH}"',
    'revision = "6de10112d785bdc37268ba3015feddfae2696bd9"': f'revision = "{PACKAGES}"',
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit(f"component pin differs: {old}")
    text = text.replace(old, new)
lock.write_text(text, encoding="utf-8")
