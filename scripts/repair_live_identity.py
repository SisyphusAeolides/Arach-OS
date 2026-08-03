#!/usr/bin/env python3
from pathlib import Path

replacements = {
    "scripts/assemble-live-root.sh": [
        ('image.get("distribution") != "Arach OS"', 'image.get("distribution") != "ArachOS"'),
        ('"distribution": "Arach OS"', '"distribution": "ArachOS"'),
    ],
    "scripts/test-live-root.sh": [
        ('assert manifest["distribution"] == "Arach OS"', 'assert manifest["distribution"] == "ArachOS"'),
        ("printf '%s\\n' 'Arach OS live-root assembly verified'", "printf '%s\\n' 'ArachOS live-root assembly verified'"),
        ("printf '%s\\n' 'Arach OS materializer rejection gate verified'", "printf '%s\\n' 'ArachOS materializer rejection gate verified'"),
        ("printf '%s\\n' 'Arach OS hardware catalog sync presence gate verified'", "printf '%s\\n' 'ArachOS hardware catalog sync presence gate verified'"),
        ("printf '%s\\n' 'Arach OS browser presence gate verified'", "printf '%s\\n' 'ArachOS browser presence gate verified'"),
    ],
}

for name, pairs in replacements.items():
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if text.count(old) != 1:
            raise SystemExit(f"{name}: expected one occurrence of {old!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
