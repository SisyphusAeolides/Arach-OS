#!/usr/bin/env python3
"""Validate installer and recovery certification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


MANIFEST = Path("production/installer-recovery.json")
EVIDENCE_ROOT = Path("production/evidence/installer-recovery")
SCENARIOS = [
    ("clean-install", "Clean install"),
    ("reinstall", "Reinstall onto an existing Arach partition"),
    ("dual-boot", "Dual-boot preservation"),
    ("encrypted-storage", "Encrypted storage create and unlock"),
    ("tpm-recovery", "TPM-backed recovery"),
    ("secure-boot", "Secure Boot and signed boot"),
    ("interrupted-partitioning", "Interrupted partitioning"),
    ("disk-full", "Disk-full safeguards"),
    ("corrupted-cache", "Corrupted cache handling"),
    ("power-loss-activation", "Power loss during activation"),
    ("failed-kernel-rollback", "Failed-kernel rollback"),
    ("rescue-media", "Rescue and repair media"),
    ("major-version-upgrade", "Major-version in-place upgrade"),
]
STATUSES = {"pending", "failed", "passed"}
OUTCOMES = {
    "success",
    "rollback-success",
    "resume-possible",
    "manual-intervention-required",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")


class RecoveryError(ValueError):
    pass


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def timestamp(value: str) -> None:
    if not value.endswith("Z"):
        raise RecoveryError("captured_at must use UTC Z form")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise RecoveryError("captured_at is not RFC 3339 compatible") from error


def load(root: Path) -> dict[str, Any]:
    path = root / MANIFEST
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecoveryError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise RecoveryError("installer recovery manifest root must be an object")
    return value


def validate_evidence(root: Path, scenario_id: str, entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise RecoveryError(f"{scenario_id}.evidence must be an array")
    expected = {
        "artifact",
        "sha256",
        "catalog_sha256",
        "plan_sha256",
        "journal_sha256",
        "captured_at",
        "revision",
        "outcome",
        "post_recovery_boot",
        "cosmic_launch",
    }
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        base = f"{scenario_id}.evidence[{index}]"
        if not isinstance(entry, dict) or set(entry) != expected:
            raise RecoveryError(f"{base} has unexpected or missing fields")
        artifact = entry["artifact"]
        if not isinstance(artifact, str) or not safe_relative(artifact):
            raise RecoveryError(f"{base}.artifact must be a safe relative path")
        if artifact in seen:
            raise RecoveryError(f"{base}.artifact is duplicated")
        seen.add(artifact)
        path = root / artifact
        try:
            path.relative_to(root / EVIDENCE_ROOT)
        except ValueError as error:
            raise RecoveryError(f"{base}.artifact must be beneath {EVIDENCE_ROOT}") from error
        if path.is_symlink() or not path.is_file():
            raise RecoveryError(f"{base}.artifact is missing or not regular")
        for field in ("sha256", "catalog_sha256", "plan_sha256", "journal_sha256"):
            if not isinstance(entry[field], str) or not SHA256_RE.fullmatch(entry[field]):
                raise RecoveryError(f"{base}.{field} must be a lowercase SHA-256 digest")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            raise RecoveryError(f"{base}.sha256 does not match the artifact")
        if not isinstance(entry["revision"], str) or not REVISION_RE.fullmatch(entry["revision"]):
            raise RecoveryError(f"{base}.revision must be a full Git object ID")
        if not isinstance(entry["captured_at"], str):
            raise RecoveryError(f"{base}.captured_at must be a timestamp")
        timestamp(entry["captured_at"])
        if entry["outcome"] not in OUTCOMES:
            raise RecoveryError(f"{base}.outcome is invalid")
        if not isinstance(entry["post_recovery_boot"], bool) or not isinstance(entry["cosmic_launch"], bool):
            raise RecoveryError(f"{base} boot and COSMIC results must be booleans")
        validated.append(entry)
    return validated


def audit(root: Path, manifest: dict[str, Any]) -> dict[str, int]:
    if set(manifest) != {"format", "distribution", "scenarios"}:
        raise RecoveryError("installer recovery manifest has invalid fields")
    if manifest["format"] != 1 or manifest["distribution"] != "Arach OS":
        raise RecoveryError("installer recovery manifest identity is invalid")
    scenarios = manifest["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) != len(SCENARIOS):
        raise RecoveryError("installer recovery manifest must contain thirteen scenarios")

    counts = {status: 0 for status in STATUSES}
    for index, ((expected_id, expected_title), scenario) in enumerate(zip(SCENARIOS, scenarios, strict=True)):
        base = f"scenarios[{index}]"
        if not isinstance(scenario, dict) or set(scenario) != {"id", "title", "status", "blocker", "evidence"}:
            raise RecoveryError(f"{base} has invalid fields")
        if scenario["id"] != expected_id or scenario["title"] != expected_title:
            raise RecoveryError(f"{base} differs from the canonical scenario order")
        status = scenario["status"]
        if status not in STATUSES:
            raise RecoveryError(f"{base}.status is invalid")
        entries = validate_evidence(root, expected_id, scenario["evidence"])
        blocker = scenario["blocker"]
        if status == "pending":
            if entries:
                raise RecoveryError(f"{base} pending scenario cannot carry evidence")
            if not isinstance(blocker, str) or not blocker.strip():
                raise RecoveryError(f"{base} pending scenario requires a blocker")
        elif status == "failed":
            if not entries:
                raise RecoveryError(f"{base} failed scenario requires failure evidence")
            if not isinstance(blocker, str) or not blocker.strip():
                raise RecoveryError(f"{base} failed scenario requires a blocker")
        else:
            if blocker is not None:
                raise RecoveryError(f"{base} passed scenario cannot retain a blocker")
            accepted = any(
                entry["outcome"] in {"success", "rollback-success", "resume-possible"}
                and entry["post_recovery_boot"]
                and entry["cosmic_launch"]
                for entry in entries
            )
            if not accepted:
                raise RecoveryError(f"{base} passed scenario lacks successful boot and COSMIC evidence")
        counts[status] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        counts = audit(root, load(root))
    except RecoveryError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"installer recovery: {counts['passed']}/13 passed, "
        f"{counts['failed']} failed, {counts['pending']} pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
