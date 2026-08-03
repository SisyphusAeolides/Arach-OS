#!/usr/bin/env python3
from pathlib import Path
import subprocess

matrix = Path("scripts/verify_control_matrices.py")
text = matrix.read_text(encoding="utf-8")
replacements = {
'''            or len(components) != len(set(components))
            or not all(isinstance(component, str) and component.strip() for component in components)
''': '''            or not all(isinstance(component, str) and component.strip() for component in components)
            or len(components) != len(set(components))
''',
'''            or len(required_evidence) != len(set(required_evidence))
            or not set(required_evidence) <= EVIDENCE_KINDS
''': '''            or not all(isinstance(kind, str) for kind in required_evidence)
            or len(required_evidence) != len(set(required_evidence))
            or not set(required_evidence) <= EVIDENCE_KINDS
''',
'''            or len(required_environments) != len(set(required_environments))
            or not set(required_environments) <= ENVIRONMENTS
''': '''            or not all(isinstance(environment, str) for environment in required_environments)
            or len(required_environments) != len(set(required_environments))
            or not set(required_environments) <= ENVIRONMENTS
''',
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit("control matrix type guard differs")
    text = text.replace(old, new)
matrix.write_text(text, encoding="utf-8")

recovery = Path("scripts/verify_installer_recovery.py")
text = recovery.read_text(encoding="utf-8")
replacements = {
'''        if entry["outcome"] not in OUTCOMES:
            raise RecoveryError(f"{base}.outcome is invalid")
''': '''        if not isinstance(entry["outcome"], str) or entry["outcome"] not in OUTCOMES:
            raise RecoveryError(f"{base}.outcome is invalid")
''',
'''        status = scenario["status"]
        if status not in STATUSES:
            raise RecoveryError(f"{base}.status is invalid")
''': '''        status = scenario["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise RecoveryError(f"{base}.status is invalid")
''',
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit("installer recovery type guard differs")
    text = text.replace(old, new)
recovery.write_text(text, encoding="utf-8")

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
