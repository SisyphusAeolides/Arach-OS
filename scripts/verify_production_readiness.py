#!/usr/bin/env python3
"""Validate the ArachOS production-readiness ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

FORMAT = 1
DISTRIBUTION = "ArachOS"
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
PLACEHOLDER_EVIDENCE_RE = re.compile(
    rb"\b(?:mock|placeholder|synthetic|sample|example[ -]only)\b", re.IGNORECASE
)

CANONICAL_GATES = (
    (1, "cosmic-lifecycle", "Full COSMIC lifecycle", "docs/COSMIC_LIFECYCLE_GATE.md"),
    (2, "linux-posix-compatibility", "Complete Linux/POSIX compatibility", "docs/LINUX_COMPAT_GATE.md"),
    (3, "hardware-driver-coverage", "Production hardware and driver coverage", "docs/HARDWARE_COVERAGE_GATE.md"),
    (4, "corinth-repository-service", "Automatic Corinth repository service", "docs/CORINTH_AUTO_INDEXER_GATE.md"),
    (5, "package-semantics", "Broader package semantics", "docs/PACKAGE_SEMANTICS_GATE.md"),
    (6, "dynamic-compatibility-workers", "Dynamic compatibility workers", "docs/DYNAMIC_COMPATIBILITY_WORKERS_GATE.md"),
    (7, "application-compatibility-tiers", "Linux application compatibility tiers", "docs/APPLICATION_COMPATIBILITY_GATE.md"),
    (8, "package-repository", "Complete the package repository", "docs/REPO_COMPLETENESS_GATE.md"),
    (9, "installer-recovery", "Installer and recovery certification", "docs/INSTALLER_RECOVERY_GATE.md"),
    (10, "desktop-services", "Desktop services", "docs/DESKTOP_SERVICES_GATE.md"),
    (11, "security-qualification", "Security qualification", "docs/SECURITY_GATE.md"),
    (12, "hardware-lab-release", "Hardware lab and release operations", "docs/HARDWARE_LAB_GATE.md"),
    (13, "universal-route", "Universal route statement", "docs/UNIVERSAL_ROUTE_GATE.md"),
    (14, "release-integrity-promotion", "Release integrity and promotion", "docs/RELEASE_INTEGRITY_GATE.md"),
)
COMPONENT_LABELS = {
    "Arach-Kernel": "arach-kernel",
    "Slope": "slope",
    "Push": "push",
    "Granite": "granite",
    "Corinth": "corinth",
    "Arach-Packages": "arach-packages",
    "Arach-HWD": "arach-hwd",
}
KNOWN_COMPONENTS = {"ArachOS", *COMPONENT_LABELS}


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


def parse_timestamp(value: str, path: str) -> datetime:
    if not value.endswith("Z"):
        fail(path, "timestamp must use UTC Z form")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(path, "timestamp must be RFC 3339 compatible")


def is_placeholder_revision(value: str) -> bool:
    return len(set(value)) == 1


def is_mock_evidence(path: str) -> bool:
    return any(
        part.lower().startswith(("mock", "placeholder", "synthetic", "sample"))
        for part in Path(path).parts
    )


def evidence_contains_placeholder(path: Path) -> bool:
    return bool(PLACEHOLDER_EVIDENCE_RE.search(path.read_bytes()))


def require_regular_evidence(root: Path, value: str, base: str) -> Path:
    evidence_root = root / "production" / "evidence"
    path = root / value
    try:
        relative = path.relative_to(root)
        path.relative_to(evidence_root)
    except ValueError:
        fail(f"{base}.path", "must be beneath production/evidence")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            fail(f"{base}.path", "cannot traverse a symlink")
    if not path.is_file():
        fail(f"{base}.path", "evidence file is missing or not regular")
    return path


def component_revisions(root: Path) -> dict[str, str]:
    path = root / "components.lock.toml"
    if path.is_symlink() or not path.is_file():
        fail("components.lock.toml", "qualified evidence requires a regular component lock")
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail("components.lock.toml", f"cannot load component lock: {error}")
    components = document.get("component")
    if not isinstance(components, list):
        fail("components.lock.toml", "component lock has no component array")
    revisions: dict[str, str] = {}
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            fail(f"components.lock.toml.component[{index}]", "must be an object")
        name = component.get("name")
        revision = component.get("revision")
        if not isinstance(name, str) or not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            fail(f"components.lock.toml.component[{index}]", "has an invalid immutable revision")
        if name in revisions:
            fail(f"components.lock.toml.component[{index}]", "duplicates a component")
        revisions[name] = revision
    return revisions


def validate_qualified_evidence_revisions(root: Path, gate: dict[str, Any], index: int) -> None:
    revisions = component_revisions(root)
    for evidence_index, item in enumerate(gate["evidence"]):
        component = item["component"]
        if component == "ArachOS":
            continue
        locked_name = COMPONENT_LABELS[component]
        if revisions.get(locked_name) != item["revision"]:
            fail(
                f"gates[{index}].evidence[{evidence_index}].revision",
                f"must match the immutable {component} component-lock revision",
            )


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
        if not isinstance(kind, str) or kind not in EVIDENCE_KINDS:
            fail(f"{base}.kind", "unknown evidence kind")
        if not isinstance(path, str) or not safe_relative(path):
            fail(f"{base}.path", "must be a safe relative path")
        resolved = require_regular_evidence(root, path, base)
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
    if not isinstance(gates, list) or len(gates) != len(CANONICAL_GATES):
        fail("gates", f"must contain exactly {len(CANONICAL_GATES)} production gates")
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
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 1
            or number > len(CANONICAL_GATES)
            or number in numbers
        ):
            fail(f"{base}.number", f"must be unique in the range 1..{len(CANONICAL_GATES)}")
        numbers.add(number)
        if not isinstance(gate_id, str) or not GATE_ID_RE.fullmatch(gate_id) or gate_id in ids:
            fail(f"{base}.id", "must be a unique lowercase kebab-case identifier")
        ids.add(gate_id)
        for field in ("title", "authority"):
            if not isinstance(gate[field], str) or not gate[field].strip():
                fail(f"{base}.{field}", "must be non-empty")
        if gate["authority"] != "ArachOS":
            fail(f"{base}.authority", "ArachOS is the release authority")
        status = gate["status"]
        if not isinstance(status, str) or status not in STATUSES:
            fail(f"{base}.status", "unknown status")
        components = gate["components"]
        if (
            not isinstance(components, list)
            or not components
            or not all(isinstance(value, str) and value.strip() for value in components)
            or len(components) != len(set(components))
        ):
            fail(f"{base}.components", "must be a non-empty unique string array")
        if not set(components) <= KNOWN_COMPONENTS:
            fail(f"{base}.components", "contains an unknown release component")
        document = gate["document"]
        if not isinstance(document, str) or not safe_relative(document) or document in documents:
            fail(f"{base}.document", "must be a unique safe relative path")
        documents.add(document)
        document_path = root / document
        if document_path.is_symlink() or not document_path.is_file():
            fail(f"{base}.document", "gate document is missing or not regular")
        if (number, gate_id, gate["title"], document) != CANONICAL_GATES[index]:
            fail(base, "identity differs from the canonical source-of-truth gate")
        dependencies = gate["depends_on"]
        if (
            not isinstance(dependencies, list)
            or not all(isinstance(value, str) and value for value in dependencies)
            or len(dependencies) != len(set(dependencies))
        ):
            fail(f"{base}.depends_on", "must be a unique string array")
        required = gate["required_evidence"]
        if (
            not isinstance(required, list)
            or not required
            or not all(isinstance(value, str) for value in required)
            or len(required) != len(set(required))
        ):
            fail(f"{base}.required_evidence", "must be a non-empty unique string array")
        if not set(required) <= EVIDENCE_KINDS:
            fail(f"{base}.required_evidence", "contains an unknown evidence kind")
        blockers = gate["blockers"]
        if not isinstance(blockers, list) or not all(isinstance(item, str) and item.strip() for item in blockers):
            fail(f"{base}.blockers", "must contain non-empty strings")
        evidence_kinds = validate_evidence(root, gate, index)
        if status == "qualified":
            if any(is_placeholder_revision(item["revision"]) for item in gate["evidence"]):
                fail(f"{base}.evidence", "contains a placeholder revision and cannot qualify")
            if any(is_mock_evidence(item["path"]) for item in gate["evidence"]):
                fail(f"{base}.evidence", "contains placeholder artifact names and cannot qualify")
            if any(evidence_contains_placeholder(root / item["path"]) for item in gate["evidence"]):
                fail(f"{base}.evidence", "contains placeholder artifact content and cannot qualify")
            if blockers:
                fail(f"{base}.blockers", "qualified gates cannot retain blockers")
            missing = set(required) - evidence_kinds
            if missing:
                fail(f"{base}.evidence", f"missing required evidence kinds: {sorted(missing)}")
            if not isinstance(gate["qualified_at"], str):
                fail(f"{base}.qualified_at", "qualified gate requires a timestamp")
            qualified_at = parse_timestamp(gate["qualified_at"], f"{base}.qualified_at")
            for evidence_index, item in enumerate(gate["evidence"]):
                captured_at = parse_timestamp(
                    item["captured_at"], f"{base}.evidence[{evidence_index}].captured_at"
                )
                if captured_at > qualified_at:
                    fail(
                        f"{base}.evidence[{evidence_index}].captured_at",
                        "cannot be later than gate qualification",
                    )
            validate_qualified_evidence_revisions(root, gate, index)
            if not isinstance(gate["qualified_revision"], str) or not REVISION_RE.fullmatch(gate["qualified_revision"]):
                fail(f"{base}.qualified_revision", "qualified gate requires a full Git object ID")
            if is_placeholder_revision(gate["qualified_revision"]):
                fail(f"{base}.qualified_revision", "placeholder revisions cannot qualify a gate")
        else:
            if not blockers:
                fail(f"{base}.blockers", "unqualified gates must state at least one blocker")
            if gate["qualified_at"] is not None or gate["qualified_revision"] is not None:
                fail(base, "unqualified gate cannot carry qualification metadata")
    if numbers != set(range(1, len(CANONICAL_GATES) + 1)):
        fail("gates", f"gate numbers must cover 1 through {len(CANONICAL_GATES)} exactly")
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
    for index, gate in enumerate(gates):
        document_text = (root / gate["document"]).read_text(encoding="utf-8")
        if f"## Current status\n\n`{gate['status']}`" not in document_text:
            fail(f"gates[{index}].document", "current status does not match the ledger")
    tracker_path = root / TRACKER_PATH
    if tracker_path.is_symlink() or not tracker_path.is_file():
        fail(TRACKER_PATH, "tracker is missing or not regular")
    tracker = tracker_path.read_text(encoding="utf-8")
    for gate in gates:
        if f"## {gate['number']}. {gate['title']}" not in tracker:
            fail(TRACKER_PATH, f"missing gate heading {gate['number']}. {gate['title']}")
        if f"[`{Path(gate['document']).name}`]" not in tracker:
            fail(TRACKER_PATH, f"missing link for {gate['document']}")
        if f"- Current status: `{gate['status']}`" not in tracker:
            fail(TRACKER_PATH, f"status for gate {gate['number']} does not match the ledger")


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
        f"ArachOS production readiness: {counts['qualified']}/{len(CANONICAL_GATES)} qualified, "
        f"{counts['in_progress']} in progress, {counts['blocked']} blocked"
    ]
    lines.extend(
        f"{gate['number']:>2}. {gate['status']:<11} {gate['title']}"
        for gate in manifest["gates"]
    )
    return "\n".join(lines)


def require_production_ready(manifest: dict[str, Any]) -> None:
    unqualified = [
        f"{gate['number']}. {gate['title']} ({gate['status']})"
        for gate in manifest["gates"]
        if gate["status"] != "qualified"
    ]
    if unqualified:
        fail("gates", "production release remains blocked by: " + "; ".join(unqualified))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--require-production-ready", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        manifest = load_json(root / MANIFEST_PATH)
        validate_manifest(root, manifest)
        if args.require_production_ready:
            require_production_ready(manifest)
    except (OSError, ReadinessError) as error:
        print(error, file=sys.stderr)
        return 1
    if args.report:
        print(report(manifest))
    else:
        print("production readiness ledger validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
