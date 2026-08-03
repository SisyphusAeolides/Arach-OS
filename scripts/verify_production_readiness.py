#!/usr/bin/env python3
"""Validate the Arach OS production-readiness ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

FORMAT = 1
DISTRIBUTION = "Arach OS"
MANIFEST_PATH = "production/readiness.json"
TRACKER_PATH = "docs/PRODUCTION_READINESS.md"
STATUSES = {"blocked", "in_progress", "qualified"}
EVIDENCE_KINDS = {
    "attestation",
    "catalog",
    "hardware-report",
    "package-report",
    "recovery-report",
    "release-report",
    "reproducibility-report",
    "route-matrix",
    "sbom",
    "security-report",
    "serial-log",
    "test-report",
    "threat-model",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")
GATE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ReadinessError(ValueError):
    pass


def fail(path: str, message: str) -> None:
    raise ReadinessError(f"{path}: {message}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(str(path), str(error))
    except json.JSONDecodeError as error:
        fail(str(path), f"invalid JSON: {error}")
    if not isinstance(value, dict):
        fail(str(path), "root must be an object")
    return value


def safe_relative(path: str) -> bool:
    candidate = Path(path)
    return bool(path) and not candidate.is_absolute() and ".." not in candidate.parts


def parse_timestamp(value: str, path: str) -> None:
    if not value.endswith("Z"):
        fail(path, "timestamp must use UTC Z form")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(path, "timestamp must be RFC 3339 compatible")


def validate_evidence(root: Path, gate: dict[str, Any], index: int) -> set[str]:
    evidence = gate.get("evidence")
    if not isinstance(evidence, list):
        fail(f"gates[{index}].evidence", "must be an array")
    kinds: set[str] = set()
    seen_paths: set[str] = set()
    for evidence_index, item in enumerate(evidence):
        base = f"gates[{index}].evidence[{evidence_index}]"
        if not isinstance(item, dict):
            fail(base, "must be an object")
        expected = {"kind", "path", "sha256", "captured_at", "component", "revision"}
        if set(item) != expected:
            fail(base, f"fields must be exactly {sorted(expected)}")
        kind = item["kind"]
        path = item["path"]
        digest = item["sha256"]
        revision = item["revision"]
        component = item["component"]
        if kind not in EVIDENCE_KINDS:
            fail(f"{base}.kind", "unknown evidence kind")
        if not isinstance(path, str) or not safe_relative(path):
            fail(f"{base}.path", "must be a safe relative path")
        evidence_root = root / "production" / "evidence"
        resolved = root / path
        try:
            resolved.relative_to(evidence_root)
        except ValueError:
            fail(f"{base}.path", "must be beneath production/evidence")
        if path in seen_paths:
            fail(f"{base}.path", "duplicate evidence path")
        seen_paths.add(path)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            fail(f"{base}.sha256", "must be a lowercase SHA-256 digest")
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            fail(f"{base}.revision", "must be a full lowercase Git object ID")
        if not isinstance(component, str) or component not in gate["components"]:
            fail(f"{base}.component", "must name one of the gate components")
        if not isinstance(item["captured_at"], str):
            fail(f"{base}.captured_at", "must be a timestamp")
        parse_timestamp(item["captured_at"], f"{base}.captured_at")
        if not resolved.is_file():
            fail(f"{base}.path", "evidence file is missing")
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual != digest:
            fail(f"{base}.sha256", "does not match the evidence file")
        kinds.add(kind)
    return kinds


def validate_manifest(root: Path, manifest: dict[str, Any]) -> None:
    if set(manifest) != {"format", "distribution", "policy", "routes", "gates"}:
        fail(MANIFEST_PATH, "unexpected or missing top-level fields")
    if manifest["format"] != FORMAT or manifest["distribution"] != DISTRIBUTION:
        fail(MANIFEST_PATH, "format or distribution identity differs from the release contract")
    policy = manifest["policy"]
    if policy != {
        "fail_closed": True,
        "evidence_root": "production/evidence",
        "qualified_status": "qualified",
    }:
        fail("policy", "must retain the fail-closed evidence policy")
    expected_routes = ["native", "rebuilt", "compatibility-runtime", "container", "managed-vm"]
    if manifest["routes"] != expected_routes:
        fail("routes", "must enumerate the canonical workload routes in order")
    gates = manifest["gates"]
    if not isinstance(gates, list) or len(gates) != 13:
        fail("gates", "must contain exactly thirteen production gates")
    ids: set[str] = set()
    numbers: set[int] = set()
    documents: set[str] = set()
    for index, gate in enumerate(gates):
        base = f"gates[{index}]"
        if not isinstance(gate, dict):
            fail(base, "must be an object")
        expected = {
            "number", "id", "title", "status", "authority", "components", "document",
            "depends_on", "required_evidence", "evidence", "blockers", "qualified_at",
            "qualified_revision",
        }
        if set(gate) != expected:
            fail(base, f"fields must be exactly {sorted(expected)}")
        number = gate["number"]
        gate_id = gate["id"]
        if not isinstance(number, int) or number < 1 or number > 13 or number in numbers:
            fail(f"{base}.number", "must be unique in the range 1..13")
        numbers.add(number)
        if not isinstance(gate_id, str) or not GATE_ID_RE.fullmatch(gate_id) or gate_id in ids:
            fail(f"{base}.id", "must be a unique lowercase kebab-case identifier")
        ids.add(gate_id)
        for field in ("title", "authority"):
            if not isinstance(gate[field], str) or not gate[field].strip():
                fail(f"{base}.{field}", "must be non-empty")
        if gate["authority"] != "Arach-OS":
            fail(f"{base}.authority", "Arach-OS is the release authority")
        status = gate["status"]
        if status not in STATUSES:
            fail(f"{base}.status", "unknown status")
        components = gate["components"]
        if not isinstance(components, list) or not components or len(components) != len(set(components)):
            fail(f"{base}.components", "must be a non-empty unique array")
        if not all(isinstance(value, str) and value.strip() for value in components):
            fail(f"{base}.components", "component names must be non-empty strings")
        document = gate["document"]
        if not isinstance(document, str) or not safe_relative(document) or document in documents:
            fail(f"{base}.document", "must be a unique safe relative path")
        documents.add(document)
        if not (root / document).is_file():
            fail(f"{base}.document", "gate document is missing")
        dependencies = gate["depends_on"]
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)):
            fail(f"{base}.depends_on", "must be a unique array")
        required = gate["required_evidence"]
        if not isinstance(required, list) or not required or len(required) != len(set(required)):
            fail(f"{base}.required_evidence", "must be a non-empty unique array")
        if not set(required) <= EVIDENCE_KINDS:
            fail(f"{base}.required_evidence", "contains an unknown evidence kind")
        blockers = gate["blockers"]
        if not isinstance(blockers, list) or not all(isinstance(item, str) and item.strip() for item in blockers):
            fail(f"{base}.blockers", "must contain non-empty strings")
        evidence_kinds = validate_evidence(root, gate, index)
        if status == "qualified":
            if blockers:
                fail(f"{base}.blockers", "qualified gates cannot retain blockers")
            missing = set(required) - evidence_kinds
            if missing:
                fail(f"{base}.evidence", f"missing required evidence kinds: {sorted(missing)}")
            if not isinstance(gate["qualified_at"], str):
                fail(f"{base}.qualified_at", "qualified gate requires a timestamp")
            parse_timestamp(gate["qualified_at"], f"{base}.qualified_at")
            if not isinstance(gate["qualified_revision"], str) or not REVISION_RE.fullmatch(gate["qualified_revision"]):
                fail(f"{base}.qualified_revision", "qualified gate requires a full Git object ID")
        else:
            if not blockers:
                fail(f"{base}.blockers", "unqualified gates must state at least one blocker")
            if gate["qualified_at"] is not None or gate["qualified_revision"] is not None:
                fail(base, "unqualified gate cannot carry qualification metadata")
    if numbers != set(range(1, 14)):
        fail("gates", "gate numbers must cover 1 through 13 exactly")
    for index, gate in enumerate(gates):
        for dependency in gate["depends_on"]:
            if dependency == gate["id"] or dependency not in ids:
                fail(f"gates[{index}].depends_on", "contains an invalid dependency")
    detect_cycles(gates)
    by_id = {gate["id"]: gate for gate in gates}
    for index, gate in enumerate(gates):
        if gate["status"] == "qualified":
            unqualified = [dep for dep in gate["depends_on"] if by_id[dep]["status"] != "qualified"]
            if unqualified:
                fail(f"gates[{index}].depends_on", f"qualified gate depends on unqualified gates: {unqualified}")
    tracker = (root / TRACKER_PATH).read_text(encoding="utf-8")
    for gate in gates:
        if f"## {gate['number']}. {gate['title']}" not in tracker:
            fail(TRACKER_PATH, f"missing gate heading {gate['number']}. {gate['title']}")
        if f"[`{Path(gate['document']).name}`]" not in tracker:
            fail(TRACKER_PATH, f"missing link for {gate['document']}")


def detect_cycles(gates: list[dict[str, Any]]) -> None:
    graph = {gate["id"]: gate["depends_on"] for gate in gates}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            fail("gates.depends_on", f"dependency cycle includes {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def report(manifest: dict[str, Any]) -> str:
    counts = {status: 0 for status in sorted(STATUSES)}
    for gate in manifest["gates"]:
        counts[gate["status"]] += 1
    lines = [
        f"Arach OS production readiness: {counts['qualified']}/13 qualified, "
        f"{counts['in_progress']} in progress, {counts['blocked']} blocked"
    ]
    lines.extend(
        f"{gate['number']:>2}. {gate['status']:<11} {gate['title']}"
        for gate in manifest["gates"]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        manifest = load_json(root / MANIFEST_PATH)
        validate_manifest(root, manifest)
    except ReadinessError as error:
        print(error, file=sys.stderr)
        return 1
    if args.report:
        print(report(manifest))
    else:
        print("production readiness ledger validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
