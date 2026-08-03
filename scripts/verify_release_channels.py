#!/usr/bin/env python3
"""Validate Arach OS release channel policy and active release records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


POLICY_PATH = Path("production/release-channels.json")
READINESS_PATH = Path("production/readiness.json")
EVIDENCE_ROOT = Path("production/evidence/release-operations")
CHANNELS = ["development", "testing", "stable"]
EVIDENCE_KINDS = {
    "attestation",
    "hardware-report",
    "recovery-report",
    "release-report",
    "reproducibility-report",
    "sbom",
    "security-report",
    "test-report",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


class ReleasePolicyError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ReleasePolicyError(f"file is not regular: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleasePolicyError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReleasePolicyError(f"root must be an object: {path}")
    return value


def parse_timestamp(value: str, path: str) -> None:
    if not value.endswith("Z"):
        raise ReleasePolicyError(f"{path} must use UTC Z form")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReleasePolicyError(f"{path} is not RFC 3339 compatible") from error


def safe_relative(value: str) -> bool:
    candidate = Path(value)
    return (
        bool(value)
        and not candidate.is_absolute()
        and ".." not in candidate.parts
        and all(part not in {"", "."} for part in candidate.parts)
    )


def unique_strings(value: Any, path: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ReleasePolicyError(f"{path} must be an array")
    if not allow_empty and not value:
        raise ReleasePolicyError(f"{path} must not be empty")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ReleasePolicyError(f"{path} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ReleasePolicyError(f"{path} must not contain duplicates")
    return value


def readiness_status(root: Path) -> dict[str, str]:
    document = load_json(root / READINESS_PATH)
    gates = document.get("gates")
    if not isinstance(gates, list):
        raise ReleasePolicyError("readiness gate array is missing")
    result: dict[str, str] = {}
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ReleasePolicyError(f"readiness.gates[{index}] must be an object")
        gate_id = gate.get("id")
        status = gate.get("status")
        if not isinstance(gate_id, str) or not isinstance(status, str):
            raise ReleasePolicyError(f"readiness.gates[{index}] has invalid identity")
        if gate_id in result:
            raise ReleasePolicyError(f"readiness gate is duplicated: {gate_id}")
        result[gate_id] = status
    return result


def validate_evidence(
    root: Path,
    release: dict[str, Any],
    base: str,
) -> set[str]:
    entries = release["evidence"]
    if not isinstance(entries, list):
        raise ReleasePolicyError(f"{base}.evidence must be an array")
    expected = {
        "kind",
        "path",
        "sha256",
        "captured_at",
        "revision",
        "environment",
    }
    kinds: set[str] = set()
    paths: set[str] = set()
    for index, entry in enumerate(entries):
        item = f"{base}.evidence[{index}]"
        if not isinstance(entry, dict) or set(entry) != expected:
            raise ReleasePolicyError(f"{item} has unexpected or missing fields")
        kind = entry["kind"]
        if not isinstance(kind, str) or kind not in EVIDENCE_KINDS:
            raise ReleasePolicyError(f"{item}.kind is invalid")
        path_value = entry["path"]
        if not isinstance(path_value, str) or not safe_relative(path_value):
            raise ReleasePolicyError(f"{item}.path must be a safe relative path")
        if path_value in paths:
            raise ReleasePolicyError(f"{item}.path is duplicated")
        paths.add(path_value)
        artifact = root / path_value
        try:
            artifact.relative_to(root / EVIDENCE_ROOT)
        except ValueError as error:
            raise ReleasePolicyError(
                f"{item}.path must be beneath {EVIDENCE_ROOT}"
            ) from error
        if artifact.is_symlink() or not artifact.is_file():
            raise ReleasePolicyError(f"{item}.path is missing or not regular")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ReleasePolicyError(f"{item}.sha256 must be a lowercase SHA-256 digest")
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
            raise ReleasePolicyError(f"{item}.sha256 does not match the artifact")
        captured_at = entry["captured_at"]
        if not isinstance(captured_at, str):
            raise ReleasePolicyError(f"{item}.captured_at must be a timestamp")
        parse_timestamp(captured_at, f"{item}.captured_at")
        revision = entry["revision"]
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            raise ReleasePolicyError(f"{item}.revision must be a full Git object ID")
        environment = entry["environment"]
        if environment not in {"continuous-integration", "hardware-lab", "independent-builder", "release-operations"}:
            raise ReleasePolicyError(f"{item}.environment is invalid")
        kinds.add(kind)
    return kinds


def validate(root: Path, policy: dict[str, Any]) -> Counter[str]:
    if set(policy) != {
        "format",
        "distribution",
        "channels",
        "mirrors",
        "promotion",
        "active_releases",
    }:
        raise ReleasePolicyError("release channel policy has invalid top-level fields")
    if (
        not isinstance(policy["format"], int)
        or isinstance(policy["format"], bool)
        or policy["format"] != 1
        or policy["distribution"] != "Arach OS"
    ):
        raise ReleasePolicyError("release channel policy identity is invalid")

    channels = policy["channels"]
    if not isinstance(channels, list) or len(channels) != len(CHANNELS):
        raise ReleasePolicyError("release channel policy must define three channels")
    readiness = readiness_status(root)
    by_name: dict[str, dict[str, Any]] = {}
    for index, (expected_name, channel) in enumerate(zip(CHANNELS, channels, strict=True)):
        base = f"channels[{index}]"
        expected_fields = {
            "name",
            "rank",
            "retained_generations",
            "minimum_soak_seconds",
            "required_readiness_gates",
            "required_evidence",
            "allow_direct_publish",
            "rollback_generations",
        }
        if not isinstance(channel, dict) or set(channel) != expected_fields:
            raise ReleasePolicyError(f"{base} has unexpected or missing fields")
        if channel["name"] != expected_name or channel["rank"] != index:
            raise ReleasePolicyError(f"{base} differs from canonical channel order")
        for field in ("retained_generations", "minimum_soak_seconds", "rollback_generations"):
            if (
                not isinstance(channel[field], int)
                or isinstance(channel[field], bool)
                or channel[field] < 0
            ):
                raise ReleasePolicyError(f"{base}.{field} must be a non-negative integer")
        if channel["retained_generations"] < 2:
            raise ReleasePolicyError(f"{base}.retained_generations must retain rollback history")
        if not 1 <= channel["rollback_generations"] < channel["retained_generations"]:
            raise ReleasePolicyError(f"{base}.rollback_generations is invalid")
        gates = unique_strings(
            channel["required_readiness_gates"],
            f"{base}.required_readiness_gates",
            allow_empty=expected_name == "development",
        )
        unknown = set(gates) - set(readiness)
        if unknown:
            raise ReleasePolicyError(f"{base} references unknown readiness gates: {sorted(unknown)}")
        evidence = unique_strings(channel["required_evidence"], f"{base}.required_evidence")
        if not set(evidence) <= EVIDENCE_KINDS:
            raise ReleasePolicyError(f"{base}.required_evidence contains an invalid kind")
        if not isinstance(channel["allow_direct_publish"], bool):
            raise ReleasePolicyError(f"{base}.allow_direct_publish must be boolean")
        if channel["allow_direct_publish"] != (expected_name == "development"):
            raise ReleasePolicyError(f"{base}.allow_direct_publish violates promotion policy")
        by_name[expected_name] = channel

    mirrors = policy["mirrors"]
    if mirrors != {
        "minimum_quorum": 2,
        "maximum_staleness_seconds": 900,
        "require_signed_root": True,
        "require_consistent_snapshot": True,
        "reject_sequence_downgrade": True,
    }:
        raise ReleasePolicyError("mirror policy must remain fail-closed")
    promotion = policy["promotion"]
    if promotion != {
        "require_previous_channel": True,
        "require_exact_component_lock": True,
        "require_exact_package_generation": True,
        "require_reproducible_image": True,
        "require_rollback_drill": True,
        "require_advisory": True,
    }:
        raise ReleasePolicyError("promotion policy must retain all production safeguards")

    releases = policy["active_releases"]
    if not isinstance(releases, list):
        raise ReleasePolicyError("active_releases must be an array")
    expected_release_fields = {
        "channel",
        "sequence",
        "version",
        "published_at",
        "revision",
        "components_lock_sha256",
        "package_generation_sha256",
        "image_sha256",
        "signature_sha256",
        "promoted_from_sequence",
        "soak_seconds",
        "mirror_count",
        "rollback_tested",
        "advisory",
        "evidence",
    }
    seen_versions: set[tuple[str, str]] = set()
    by_channel: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for index, release in enumerate(releases):
        base = f"active_releases[{index}]"
        if not isinstance(release, dict) or set(release) != expected_release_fields:
            raise ReleasePolicyError(f"{base} has unexpected or missing fields")
        channel_name = release["channel"]
        if not isinstance(channel_name, str) or channel_name not in by_name:
            raise ReleasePolicyError(f"{base}.channel is invalid")
        channel = by_name[channel_name]
        sequence = release["sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
            raise ReleasePolicyError(f"{base}.sequence must be positive")
        version = release["version"]
        if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
            raise ReleasePolicyError(f"{base}.version is invalid")
        if (channel_name, version) in seen_versions:
            raise ReleasePolicyError(f"{base}.version is duplicated in the channel")
        seen_versions.add((channel_name, version))
        published_at = release["published_at"]
        if not isinstance(published_at, str):
            raise ReleasePolicyError(f"{base}.published_at must be a timestamp")
        parse_timestamp(published_at, f"{base}.published_at")
        revision = release["revision"]
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            raise ReleasePolicyError(f"{base}.revision must be a full Git object ID")
        for field in (
            "components_lock_sha256",
            "package_generation_sha256",
            "image_sha256",
            "signature_sha256",
        ):
            digest = release[field]
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                raise ReleasePolicyError(f"{base}.{field} must be a SHA-256 digest")
        soak = release["soak_seconds"]
        if not isinstance(soak, int) or isinstance(soak, bool) or soak < channel["minimum_soak_seconds"]:
            raise ReleasePolicyError(f"{base}.soak_seconds is below the channel minimum")
        mirror_count = release["mirror_count"]
        if not isinstance(mirror_count, int) or isinstance(mirror_count, bool) or mirror_count < mirrors["minimum_quorum"]:
            raise ReleasePolicyError(f"{base}.mirror_count is below quorum")
        if not isinstance(release["rollback_tested"], bool) or not release["rollback_tested"]:
            raise ReleasePolicyError(f"{base}.rollback_tested must be true")
        advisory = release["advisory"]
        if not isinstance(advisory, str) or not safe_relative(advisory):
            raise ReleasePolicyError(f"{base}.advisory must be a safe relative path")
        advisory_path = root / advisory
        if advisory_path.is_symlink() or not advisory_path.is_file():
            raise ReleasePolicyError(f"{base}.advisory is missing or not regular")
        missing_gates = [gate for gate in channel["required_readiness_gates"] if readiness[gate] != "qualified"]
        if missing_gates:
            raise ReleasePolicyError(f"{base} requires unqualified readiness gates: {missing_gates}")
        evidence_kinds = validate_evidence(root, release, base)
        missing_evidence = set(channel["required_evidence"]) - evidence_kinds
        if missing_evidence:
            raise ReleasePolicyError(f"{base} lacks evidence kinds: {sorted(missing_evidence)}")
        promoted = release["promoted_from_sequence"]
        if channel_name == "development":
            if promoted is not None:
                raise ReleasePolicyError(f"{base}.promoted_from_sequence must be null")
        elif not isinstance(promoted, int) or isinstance(promoted, bool) or promoted <= 0:
            raise ReleasePolicyError(f"{base}.promoted_from_sequence must name a prior release")
        by_channel[channel_name].append(release)
        counts[channel_name] += 1

    for channel_name, records in by_channel.items():
        records.sort(key=lambda record: record["sequence"])
        sequences = [record["sequence"] for record in records]
        if len(sequences) != len(set(sequences)):
            raise ReleasePolicyError(f"{channel_name} contains duplicate sequences")
        if any(left >= right for left, right in zip(sequences, sequences[1:])):
            raise ReleasePolicyError(f"{channel_name} sequences are not monotonic")
        if len(records) > by_name[channel_name]["retained_generations"]:
            raise ReleasePolicyError(f"{channel_name} exceeds retained generation policy")

    for channel_name in ("testing", "stable"):
        previous_name = CHANNELS[CHANNELS.index(channel_name) - 1]
        previous_sequences = {record["sequence"] for record in by_channel[previous_name]}
        for release in by_channel[channel_name]:
            if release["promoted_from_sequence"] not in previous_sequences:
                raise ReleasePolicyError(
                    f"{channel_name} release is not promoted from retained {previous_name} evidence"
                )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        counts = validate(root, load_json(root / POLICY_PATH))
    except ReleasePolicyError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        "release channels: "
        + ", ".join(f"{channel}={counts[channel]}" for channel in CHANNELS)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
