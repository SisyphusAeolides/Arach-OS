#!/usr/bin/env python3
from pathlib import Path
import subprocess

matrix = Path("scripts/verify_control_matrices.py")
text = matrix.read_text(encoding="utf-8")
replacements = {
'''        if kind not in EVIDENCE_KINDS:
            raise ControlMatrixError(f"{item_base}.kind is invalid")
''': '''        if not isinstance(kind, str) or kind not in EVIDENCE_KINDS:
            raise ControlMatrixError(f"{item_base}.kind is invalid")
''',
'''        if environment not in ENVIRONMENTS:
            raise ControlMatrixError(f"{item_base}.environment is invalid")
''': '''        if not isinstance(environment, str) or environment not in ENVIRONMENTS:
            raise ControlMatrixError(f"{item_base}.environment is invalid")
''',
'''        if component not in control["components"]:
            raise ControlMatrixError(f"{item_base}.component is outside the control boundary")
''': '''        if not isinstance(component, str) or component not in control["components"]:
            raise ControlMatrixError(f"{item_base}.component is outside the control boundary")
''',
'''        status = control["status"]
        if status not in STATUSES:
            raise ControlMatrixError(f"{base}.status is invalid")
''': '''        status = control["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise ControlMatrixError(f"{base}.status is invalid")
''',
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

threat = Path("scripts/verify_threat_model.py")
text = threat.read_text(encoding="utf-8")
replacements = {
'''        kind = entry["kind"]
        if kind not in EVIDENCE_KINDS:
            raise ThreatModelError(f"{item}.kind is invalid")
''': '''        kind = entry["kind"]
        if not isinstance(kind, str) or kind not in EVIDENCE_KINDS:
            raise ThreatModelError(f"{item}.kind is invalid")
''',
'''        if entry["environment"] not in ENVIRONMENTS:
            raise ThreatModelError(f"{item}.environment is invalid")
''': '''        if not isinstance(entry["environment"], str) or entry["environment"] not in ENVIRONMENTS:
            raise ThreatModelError(f"{item}.environment is invalid")
''',
'''        status = threat["status"]
        if status not in STATUSES:
            raise ThreatModelError(f"{base}.status is invalid")
''': '''        status = threat["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise ThreatModelError(f"{base}.status is invalid")
''',
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit("threat model type guard differs")
    text = text.replace(old, new)
threat.write_text(text, encoding="utf-8")

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
