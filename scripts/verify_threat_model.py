#!/usr/bin/env python3
"""Validate the ArachOS structured threat model and retained evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


MODEL_PATH = Path("production/threat-model.json")
EVIDENCE_ROOT = Path("production/evidence/security")
THREAT_IDS = [f"T{number:02d}" for number in range(1, 13)]
CATEGORIES = {
    "spoofing",
    "tampering",
    "repudiation",
    "information-disclosure",
    "denial-of-service",
    "elevation-of-privilege",
}
SECURITY_PROPERTIES = {
    "authenticity",
    "availability",
    "bounded-lifetime",
    "confidentiality",
    "device-binding",
    "freshness",
    "integrity",
    "isolation",
    "recoverability",
    "reproducibility",
    "revocability",
    "revision-binding",
    "rollback-resistance",
    "traceability",
}
EVIDENCE_KINDS = {
    "attestation",
    "fuzz-report",
    "hardware-report",
    "hardening-report",
    "key-drill",
    "recovery-report",
    "release-report",
    "reproducibility-report",
    "sbom",
    "security-report",
    "soak-report",
    "test-report",
    "threat-model",
    "vulnerability-drill",
}
ENVIRONMENTS = {
    "continuous-integration",
    "design-review",
    "hardware-lab",
    "independent-builder",
    "physical-hardware",
    "qemu",
    "release-operations",
}
STATUSES = {"open", "partially-mitigated", "mitigated"}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")


class ThreatModelError(ValueError):
    pass


def load_model(root: Path) -> dict[str, Any]:
    path = root / MODEL_PATH
    if path.is_symlink() or not path.is_file():
        raise ThreatModelError(f"threat model is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ThreatModelError(f"cannot load threat model: {error}") from error
    if not isinstance(value, dict):
        raise ThreatModelError("threat model root must be an object")
    return value


def safe_relative(value: str) -> bool:
    path = Path(value)
    return (
        bool(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and all(part not in {"", "."} for part in path.parts)
    )


def nonempty_unique_strings(value: Any, path: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ThreatModelError(f"{path} must be a non-empty unique string array")
    return value


def parse_timestamp(value: str, path: str) -> None:
    if not value.endswith("Z"):
        raise ThreatModelError(f"{path} must use UTC Z form")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ThreatModelError(f"{path} is not RFC 3339 compatible") from error


def validate_evidence(
    root: Path,
    threat: dict[str, Any],
    base: str,
) -> set[str]:
    entries = threat["evidence"]
    if not isinstance(entries, list):
        raise ThreatModelError(f"{base}.evidence must be an array")
    fields = {
        "kind",
        "path",
        "sha256",
        "captured_at",
        "revision",
        "component",
        "environment",
    }
    kinds: set[str] = set()
    paths: set[str] = set()
    for index, entry in enumerate(entries):
        item = f"{base}.evidence[{index}]"
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ThreatModelError(f"{item} has unexpected or missing fields")
        kind = entry["kind"]
        if not isinstance(kind, str) or kind not in EVIDENCE_KINDS:
            raise ThreatModelError(f"{item}.kind is invalid")
        path_value = entry["path"]
        if not isinstance(path_value, str) or not safe_relative(path_value):
            raise ThreatModelError(f"{item}.path must be a safe relative path")
        if path_value in paths:
            raise ThreatModelError(f"{item}.path is duplicated")
        paths.add(path_value)
        artifact = root / path_value
        try:
            artifact.relative_to(root / EVIDENCE_ROOT)
        except ValueError as error:
            raise ThreatModelError(
                f"{item}.path must be beneath {EVIDENCE_ROOT}"
            ) from error
        if artifact.is_symlink() or not artifact.is_file():
            raise ThreatModelError(f"{item}.path is missing or not regular")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ThreatModelError(f"{item}.sha256 must be a lowercase SHA-256 digest")
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
            raise ThreatModelError(f"{item}.sha256 does not match the artifact")
        revision = entry["revision"]
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            raise ThreatModelError(f"{item}.revision must be a full Git object ID")
        captured_at = entry["captured_at"]
        if not isinstance(captured_at, str):
            raise ThreatModelError(f"{item}.captured_at must be a timestamp")
        parse_timestamp(captured_at, f"{item}.captured_at")
        component = entry["component"]
        if not isinstance(component, str) or not component.strip():
            raise ThreatModelError(f"{item}.component must be non-empty")
        if not isinstance(entry["environment"], str) or entry["environment"] not in ENVIRONMENTS:
            raise ThreatModelError(f"{item}.environment is invalid")
        kinds.add(kind)
    return kinds


def validate(root: Path, model: dict[str, Any]) -> dict[str, int]:
    if set(model) != {
        "format",
        "distribution",
        "method",
        "assets",
        "boundaries",
        "threats",
    }:
        raise ThreatModelError("threat model has unexpected or missing fields")
    if model["format"] != 1 or model["distribution"] != "ArachOS":
        raise ThreatModelError("threat model identity is invalid")
    if not isinstance(model["method"], str) or not model["method"].strip():
        raise ThreatModelError("threat model method is empty")

    assets = model["assets"]
    if not isinstance(assets, list) or not assets:
        raise ThreatModelError("assets must be a non-empty array")
    asset_ids: set[str] = set()
    for index, asset in enumerate(assets):
        base = f"assets[{index}]"
        if not isinstance(asset, dict) or set(asset) != {
            "id",
            "title",
            "owner",
            "security_properties",
        }:
            raise ThreatModelError(f"{base} has invalid fields")
        identifier = asset["id"]
        if (
            not isinstance(identifier, str)
            or not ID_RE.fullmatch(identifier)
            or identifier in asset_ids
        ):
            raise ThreatModelError(f"{base}.id is invalid or duplicated")
        asset_ids.add(identifier)
        if not isinstance(asset["title"], str) or not asset["title"].strip():
            raise ThreatModelError(f"{base}.title is empty")
        if not isinstance(asset["owner"], str) or not asset["owner"].strip():
            raise ThreatModelError(f"{base}.owner is empty")
        properties = nonempty_unique_strings(
            asset["security_properties"], f"{base}.security_properties"
        )
        if not set(properties) <= SECURITY_PROPERTIES:
            raise ThreatModelError(f"{base}.security_properties contains an invalid value")

    boundaries = model["boundaries"]
    if not isinstance(boundaries, list) or not boundaries:
        raise ThreatModelError("boundaries must be a non-empty array")
    boundary_ids: set[str] = set()
    for index, boundary in enumerate(boundaries):
        base = f"boundaries[{index}]"
        if not isinstance(boundary, dict) or set(boundary) != {
            "id",
            "from",
            "to",
            "channel",
        }:
            raise ThreatModelError(f"{base} has invalid fields")
        identifier = boundary["id"]
        if (
            not isinstance(identifier, str)
            or not ID_RE.fullmatch(identifier)
            or identifier in boundary_ids
        ):
            raise ThreatModelError(f"{base}.id is invalid or duplicated")
        boundary_ids.add(identifier)
        for field in ("from", "to", "channel"):
            if not isinstance(boundary[field], str) or not boundary[field].strip():
                raise ThreatModelError(f"{base}.{field} is empty")

    threats = model["threats"]
    if not isinstance(threats, list) or len(threats) != len(THREAT_IDS):
        raise ThreatModelError("threat model must contain twelve canonical threats")
    counts = {status: 0 for status in STATUSES}
    control_root = root.resolve()
    for index, (expected_id, threat) in enumerate(zip(THREAT_IDS, threats, strict=True)):
        base = f"threats[{index}]"
        fields = {
            "id",
            "title",
            "categories",
            "assets",
            "boundaries",
            "status",
            "controls",
            "required_evidence",
            "evidence",
            "residual_risk",
            "blockers",
        }
        if not isinstance(threat, dict) or set(threat) != fields:
            raise ThreatModelError(f"{base} has unexpected or missing fields")
        if threat["id"] != expected_id:
            raise ThreatModelError(f"{base}.id differs from canonical threat order")
        if not isinstance(threat["title"], str) or not threat["title"].strip():
            raise ThreatModelError(f"{base}.title is empty")
        categories = nonempty_unique_strings(threat["categories"], f"{base}.categories")
        if not set(categories) <= CATEGORIES:
            raise ThreatModelError(f"{base}.categories contains an invalid value")
        referenced_assets = nonempty_unique_strings(threat["assets"], f"{base}.assets")
        if not set(referenced_assets) <= asset_ids:
            raise ThreatModelError(f"{base}.assets references an unknown asset")
        referenced_boundaries = nonempty_unique_strings(
            threat["boundaries"], f"{base}.boundaries"
        )
        if not set(referenced_boundaries) <= boundary_ids:
            raise ThreatModelError(f"{base}.boundaries references an unknown boundary")
        controls = nonempty_unique_strings(threat["controls"], f"{base}.controls")
        for control in controls:
            if not safe_relative(control):
                raise ThreatModelError(f"{base}.controls contains an unsafe path")
            path = root / control
            if path.is_symlink() or not path.is_file():
                raise ThreatModelError(f"{base}.controls is missing: {control}")
            if not path.resolve().is_relative_to(control_root):
                raise ThreatModelError(f"{base}.controls escapes the repository: {control}")
        required = nonempty_unique_strings(
            threat["required_evidence"], f"{base}.required_evidence"
        )
        if not set(required) <= EVIDENCE_KINDS:
            raise ThreatModelError(f"{base}.required_evidence contains an invalid value")
        status = threat["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise ThreatModelError(f"{base}.status is invalid")
        blockers = threat["blockers"]
        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str) and blocker.strip() for blocker in blockers
        ):
            raise ThreatModelError(f"{base}.blockers must contain non-empty strings")
        evidence_kinds = validate_evidence(root, threat, base)
        if status == "mitigated":
            if blockers:
                raise ThreatModelError(f"{base}.blockers must be empty after mitigation")
            missing = set(required) - evidence_kinds
            if missing:
                raise ThreatModelError(
                    f"{base}.evidence lacks required kinds: {sorted(missing)}"
                )
            if threat["residual_risk"] is not None:
                raise ThreatModelError(
                    f"{base}.residual_risk must be null after full mitigation"
                )
        else:
            if not blockers:
                raise ThreatModelError(f"{base} requires at least one blocker")
            if (
                not isinstance(threat["residual_risk"], str)
                or not threat["residual_risk"].strip()
            ):
                raise ThreatModelError(f"{base}.residual_risk must be explicit")
        counts[status] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        counts = validate(root, load_model(root))
    except ThreatModelError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"threat model: {counts['mitigated']}/12 mitigated, "
        f"{counts['partially-mitigated']} partially mitigated, {counts['open']} open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
