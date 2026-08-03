#!/usr/bin/env python3
from pathlib import Path

path = Path("src/lib.rs")
text = path.read_text(encoding="utf-8")
old = 'pub const DISTRIBUTION: &str = "Arach OS";'
new = 'pub const DISTRIBUTION: &str = "ArachOS";'
if text.count(old) != 1:
    raise SystemExit("distribution constant differs")
path.write_text(text.replace(old, new), encoding="utf-8")
