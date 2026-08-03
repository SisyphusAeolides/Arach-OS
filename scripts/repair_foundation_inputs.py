#!/usr/bin/env python3
from pathlib import Path

path = Path("scripts/test-live-root.sh")
text = path.read_text(encoding="utf-8")

fixture = """printf '\\177ELF test Arach HWD catalog sync\\n' \\
    > \"$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd-catalog-sync\"
"""
qualification = """printf '\\177ELF test Arach HWD qualification\\n' \\
    > \"$artifacts/arach-hwd-0.1.0-1/target/release/arach-hwd-qualify\"
"""
if text.count(fixture) != 1:
    raise SystemExit("Arach HWD fixture marker differs")
text = text.replace(fixture, fixture + qualification)

assertion = 'test -s "$output/system/arach-hwd-catalog-sync"\n'
replacement = assertion + 'test -s "$output/system/arach-hwd-qualify"\n'
if text.count(assertion) != 1:
    raise SystemExit("Arach HWD assertion marker differs")
path.write_text(text.replace(assertion, replacement), encoding="utf-8")
