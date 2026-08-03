#!/usr/bin/env python3
"""Validate production control matrices and their retained evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


MATRIX_ROOT = Path("production/control-matrices")
EVIDENCE_ROOT = Path("production/evidence")
MATRICES = {
    "desktop-services": [
        "networking",
        "wifi-authentication",
        "time-synchronization",
        "dbus",
        "portals",
        "audio-bluetooth-audio",
        "credentials-authorization",
        "printing-removable-media",
        "cameras",
        "notifications",
        "updates-diagnostics",
        "locale-fonts",
        "input-accessibility",
        "power-management",
    ],
    "security": [
        "threat-models",
        "continuous-fuzzing",
        "hardening",
        "privilege-separation",
        "sandboxing",
        "key-operations",
        "sbom-attestations",
        "reproducible-builds",
        "vulnerability-response",
    ],
    "release-operations": [
        "hardware-matrix",
        "support-levels",
        "release-channels",
        "mirrors",
        "rollback-drills",
        "advisories-release-notes",
        "soak-testing",
    ],
}
STATUSES = {"pending", "implemented", "failed", "qualified"}
EVIDENCE_KINDS = {
    "attestation",
    "fuzz-report",
    "hardware-report",
    "hardening-report",
    "key-drill",
    "mirror-report",
    "recovery-report",
    "release-report",
    "reproducibility-report",
    "sbom",
    "security-report",
    "serial-log",
    "service-snapshot",
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
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")


class ControlMatrixError(ValueError):
    pass


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def parse_timestamp(value: str, path: str) -> None:
    if not value.endswith("Z"):
        raise ControlMatrixError(f"{path} must use UTC Z form")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ControlMatrixError(f"{path} is not RFC 3339 compatible") from error


def load_document(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ControlMatrixError(f"matrix is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ControlMatrixError(f"cannot load matrix {path}: {error}") from error
    if not isinstance(value, dict):
        raise ControlMatrixError(f"matrix root must be an object: {path}")
    return value


def validate_evidence(
    root: Path,
    matrix_id: str,
    control: dict[str, Any],
    base: str,
) -> tuple[set[str], set[str]]:
    evidence = control["evidence"]
    if not isinstance(evidence, list):
        raise ControlMatrixError(f"{base}.evidence must be an array")
    expected = {
        "kind",
        "path",
        "sha256",
        "captured_at",
        "revision",
        "component",
        "environment",
    }
    kinds: set[str] = set()
    environments: set[str] = set()
    paths: set[str] = set()
    for index, item in enumerate(evidence):
        item_base = f"{base}.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != expected:
            raise ControlMatrixError(f"{item_base} has unexpected or missing fields")
        kind = item["kind"]
        environment = item["environment"]
        component = item["component"]
        path_value = item["path"]
        if not isinstance(kind, str) or kind not in EVIDENCE_KINDS:
            raise ControlMatrixError(f"{item_base}.kind is invalid")
        if not isinstance(environment, str) or environment not in ENVIRONMENTS:
            raise ControlMatrixError(f"{item_base}.environment is invalid")
        if not isinstance(component, str) or component not in control["components"]:
            raise ControlMatrixError(f"{item_base}.component is outside the control boundary")
        if not isinstance(path_value, str) or not safe_relative(path_value):
            raise ControlMatrixError(f"{item_base}.path must be a safe relative path")
        if path_value in paths:
            raise ControlMatrixError(f"{item_base}.path is duplicated")
        paths.add(path_value)
        path = root / path_value
        try:
            path.relative_to(root / EVIDENCE_ROOT / matrix_id)
        except ValueError as error:
            raise ControlMatrixError(
                f"{item_base}.path must be beneath {EVIDENCE_ROOT / matrix_id}"
            ) from error
        if path.is_symlink() or not path.is_file():
            raise ControlMatrixError(f"{item_base}.path is missing or not regular")
        digest = item["sha256"]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ControlMatrixError(f"{item_base}.sha256 must be a lowercase SHA-256 digest")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ControlMatrixError(f"{item_base}.sha256 does not match the artifact")
        revision = item["revision"]
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            raise ControlMatrixError(f"{item_base}.revision must be a full Git object ID")
        captured_at = item["captured_at"]
        if not isinstance(captured_at, str):
            raise ControlMatrixError(f"{item_base}.captured_at must be a timestamp")
        parse_timestamp(captured_at, f"{item_base}.captured_at")
        kinds.add(kind)
        environments.add(environment)
    return kinds, environments


def validate_document(
    root: Path,
    document: dict[str, Any],
    expected_ids: list[str],
) -> Counter[str]:
    if set(document) != {"format", "distribution", "matrix", "title", "controls"}:
        raise ControlMatrixError("matrix has unexpected or missing top-level fields")
    if document["format"] != 1 or document["distribution"] != "ArachOS":
        raise ControlMatrixError("matrix format or distribution identity is invalid")
    matrix_id = document["matrix"]
    if not isinstance(matrix_id, str) or not ID_RE.fullmatch(matrix_id):
        raise ControlMatrixError("matrix identifier is invalid")
    if not isinstance(document["title"], str) or not document["title"].strip():
        raise ControlMatrixError("matrix title is empty")
    controls = document["controls"]
    if not isinstance(controls, list) or len(controls) != len(expected_ids):
        raise ControlMatrixError("matrix control count differs from its canonical definition")

    counts: Counter[str] = Counter()
    for index, (expected_id, control) in enumerate(zip(expected_ids, controls, strict=True)):
        base = f"{matrix_id}.controls[{index}]"
        expected_fields = {
            "id",
            "title",
            "status",
            "components",
            "required_evidence",
            "required_environments",
            "evidence",
            "blockers",
        }
        if not isinstance(control, dict) or set(control) != expected_fields:
            raise ControlMatrixError(f"{base} has unexpected or missing fields")
        if control["id"] != expected_id:
            raise ControlMatrixError(f"{base}.id differs from the canonical control order")
        if not isinstance(control["title"], str) or not control["title"].strip():
            raise ControlMatrixError(f"{base}.title is empty")
        status = control["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise ControlMatrixError(f"{base}.status is invalid")
        components = control["components"]
        if (
            not isinstance(components, list)
            or not components
            or not all(isinstance(component, str) and component.strip() for component in components)
            or len(components) != len(set(components))
        ):
            raise ControlMatrixError(f"{base}.components must be a non-empty unique string array")
        required_evidence = control["required_evidence"]
        if (
            not isinstance(required_evidence, list)
            or not required_evidence
            or not all(isinstance(kind, str) for kind in required_evidence)
            or len(required_evidence) != len(set(required_evidence))
            or not set(required_evidence) <= EVIDENCE_KINDS
        ):
            raise ControlMatrixError(f"{base}.required_evidence is invalid")
        required_environments = control["required_environments"]
        if (
            not isinstance(required_environments, list)
            or not required_environments
            or not all(isinstance(environment, str) for environment in required_environments)
            or len(required_environments) != len(set(required_environments))
            or not set(required_environments) <= ENVIRONMENTS
        ):
            raise ControlMatrixError(f"{base}.required_environments is invalid")
        blockers = control["blockers"]
        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str) and blocker.strip() for blocker in blockers
        ):
            raise ControlMatrixError(f"{base}.blockers must contain non-empty strings")

        evidence_kinds, evidence_environments = validate_evidence(root, matrix_id, control, base)
        if status == "qualified":
            if blockers:
                raise ControlMatrixError(f"{base}.blockers must be empty after qualification")
            missing_kinds = set(required_evidence) - evidence_kinds
            if missing_kinds:
                raise ControlMatrixError(
                    f"{base}.evidence lacks required kinds: {sorted(missing_kinds)}"
                )
            missing_environments = set(required_environments) - evidence_environments
            if missing_environments:
                raise ControlMatrixError(
                    f"{base}.evidence lacks required environments: {sorted(missing_environments)}"
                )
        elif status == "failed":
            if not blockers or not control["evidence"]:
                raise ControlMatrixError(f"{base} failed control requires blockers and evidence")
        else:
            if not blockers:
                raise ControlMatrixError(f"{base} unqualified control requires a blocker")
        counts[status] += 1
    return counts


def audit(root: Path) -> dict[str, Counter[str]]:
    actual = {
        path.stem
        for path in (root / MATRIX_ROOT).glob("*.json")
        if path.is_file() and not path.is_symlink()
    }
    expected_files = {
        "desktop-services",
        "security",
        "release-operations",
    }
    if actual != expected_files:
        raise ControlMatrixError(
            f"control matrix file set differs: expected={sorted(expected_files)}, actual={sorted(actual)}"
        )

    result: dict[str, Counter[str]] = {}
    for matrix_id, expected_ids in MATRICES.items():
        path = root / MATRIX_ROOT / f"{matrix_id}.json"
        document = load_document(path)
        if document.get("matrix") != matrix_id:
            raise ControlMatrixError(f"{path} declares the wrong matrix identifier")
        result[matrix_id] = validate_document(root, document, expected_ids)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        matrices = audit(root)
    except ControlMatrixError as error:
        print(error, file=sys.stderr)
        return 1
    for matrix_id, counts in matrices.items():
        total = sum(counts.values())
        print(
            f"{matrix_id}: {counts['qualified']}/{total} qualified, "
            f"{counts['implemented']} implemented, {counts['failed']} failed, "
            f"{counts['pending']} pending"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
