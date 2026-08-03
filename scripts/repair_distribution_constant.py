#!/usr/bin/env python3
from pathlib import Path
import subprocess

script = Path("scripts/repair_distribution_constant.py")
result = subprocess.run(
    ["git", "grep", "-Il", "-e", "Arach OS", "-e", "Arach-OS", "--", "."],
    check=False,
    capture_output=True,
    text=True,
)
for name in sorted(filter(None, result.stdout.splitlines())):
    path = Path(name)
    if path == script:
        continue
    data = path.read_bytes()
    updated = data.replace(b"Arach-OS", b"ArachOS").replace(b"Arach OS", b"ArachOS")
    if updated != data:
        path.write_bytes(updated)

remaining = subprocess.run(
    [
        "git",
        "grep",
        "-In",
        "-e",
        "Arach OS",
        "-e",
        "Arach-OS",
        "--",
        ".",
        ":(exclude)scripts/repair_distribution_constant.py",
    ],
    check=False,
    capture_output=True,
    text=True,
)
if remaining.returncode == 0 and remaining.stdout.strip():
    raise SystemExit(f"retired ArachOS identity remains:\n{remaining.stdout}")
