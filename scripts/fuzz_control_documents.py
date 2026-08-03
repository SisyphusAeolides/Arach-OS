#!/usr/bin/env python3
"""Deterministically fuzz production control documents and their validators."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_SEED = 0xA2A_C0DE_2026
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


class FuzzError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    name: str
    document: dict[str, Any]
    validate: Callable[[dict[str, Any]], Any]
    expected_error: type[Exception]


def load_module(name: str, path: Path) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise FuzzError(f"cannot load validator module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FuzzError(f"control document is not a regular file: {path}")
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise FuzzError(f"control document exceeds bounded size: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FuzzError(f"cannot load control document {path}: {error}") from error
    if not isinstance(value, dict):
        raise FuzzError(f"control document root is not an object: {path}")
    return value


def targets(root: Path) -> list[Target]:
    scripts = root / "scripts"
    readiness = load_module(
        "fuzz_verify_production_readiness",
        scripts / "verify_production_readiness.py",
    )
    recovery = load_module(
        "fuzz_verify_installer_recovery",
        scripts / "verify_installer_recovery.py",
    )
    controls = load_module(
        "fuzz_verify_control_matrices",
        scripts / "verify_control_matrices.py",
    )
    threats = load_module(
        "fuzz_verify_threat_model",
        scripts / "verify_threat_model.py",
    )

    result = [
        Target(
            name="readiness",
            document=load_json(root / "production/readiness.json"),
            validate=lambda document: readiness.validate_document(root, document),
            expected_error=readiness.ReadinessError,
        ),
        Target(
            name="installer-recovery",
            document=load_json(root / "production/installer-recovery.json"),
            validate=lambda document: recovery.audit(root, document),
            expected_error=recovery.RecoveryError,
        ),
        Target(
            name="threat-model",
            document=load_json(root / "production/threat-model.json"),
            validate=lambda document: threats.validate(root, document),
            expected_error=threats.ThreatModelError,
        ),
    ]
    for matrix_id, expected_ids in controls.MATRICES.items():
        result.append(
            Target(
                name=f"control-matrix:{matrix_id}",
                document=load_json(
                    root / "production/control-matrices" / f"{matrix_id}.json"
                ),
                validate=lambda document, expected_ids=expected_ids: controls.validate_document(
                    root, document, expected_ids
                ),
                expected_error=controls.ControlMatrixError,
            )
        )
    for target in result:
        target.validate(copy.deepcopy(target.document))
    return result


def mutate_bytes(source: bytes, randomizer: random.Random) -> bytes:
    value = bytearray(source)
    operation = randomizer.randrange(4)
    if operation == 0 and value:
        index = randomizer.randrange(len(value))
        value[index] = randomizer.randrange(256)
    elif operation == 1 and value:
        index = randomizer.randrange(len(value))
        del value[index]
    elif operation == 2:
        index = randomizer.randrange(len(value) + 1)
        value[index:index] = bytes([randomizer.randrange(256)])
    else:
        if value:
            start = randomizer.randrange(len(value))
            stop = min(len(value), start + randomizer.randrange(1, 17))
            value[start:stop] = bytes(
                randomizer.randrange(256) for _ in range(randomizer.randrange(0, 17))
            )
    return bytes(value)


def containers(value: Any) -> list[Any]:
    found: list[Any] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            found.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            found.append(current)
            stack.extend(current)
    return found


def mutate_structure(source: dict[str, Any], randomizer: random.Random) -> dict[str, Any]:
    document = copy.deepcopy(source)
    candidates = containers(document)
    target = randomizer.choice(candidates)
    if isinstance(target, dict):
        operation = randomizer.randrange(4)
        keys = list(target)
        if operation == 0 and keys:
            del target[randomizer.choice(keys)]
        elif operation == 1:
            target[f"unknown_{randomizer.randrange(1_000_000)}"] = None
        elif operation == 2 and keys:
            key = randomizer.choice(keys)
            target[key] = randomizer.choice(
                [None, True, False, 0, -1, "", [], {}, [None], {"unexpected": True}]
            )
        elif keys:
            key = randomizer.choice(keys)
            target[key] = copy.deepcopy(target[key])
    else:
        operation = randomizer.randrange(4)
        if operation == 0 and target:
            del target[randomizer.randrange(len(target))]
        elif operation == 1 and target:
            target.insert(randomizer.randrange(len(target) + 1), copy.deepcopy(target[0]))
        elif operation == 2:
            target.insert(
                randomizer.randrange(len(target) + 1),
                randomizer.choice([None, True, 0, "", {}, []]),
            )
        else:
            target.reverse()
    return document


def exercise(target: Target, document: dict[str, Any]) -> str:
    try:
        target.validate(document)
    except target.expected_error:
        return "semantic-reject"
    except Exception as error:
        raise FuzzError(
            f"{target.name} validator crashed with {type(error).__name__}: {error}"
        ) from error
    return "accepted"


def run(root: Path, cases: int, seed: int) -> dict[str, Any]:
    if cases < 1 or cases > 100_000:
        raise FuzzError("case count must be between 1 and 100000")
    randomizer = random.Random(seed)
    loaded = targets(root)
    counters = {
        target.name: {
            "cases": 0,
            "parse-reject": 0,
            "semantic-reject": 0,
            "accepted": 0,
        }
        for target in loaded
    }

    for index in range(cases):
        target = loaded[index % len(loaded)]
        counts = counters[target.name]
        counts["cases"] += 1
        if index % 2 == 0:
            canonical = json.dumps(
                target.document,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            mutated = mutate_bytes(canonical, randomizer)
            if len(mutated) > MAX_DOCUMENT_BYTES:
                raise FuzzError("mutated document exceeded bounded size")
            try:
                text = mutated.decode("utf-8")
                document = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError):
                counts["parse-reject"] += 1
                continue
            if not isinstance(document, dict):
                counts["semantic-reject"] += 1
                continue
        else:
            document = mutate_structure(target.document, randomizer)
        counts[exercise(target, document)] += 1

    total = sum(counter["cases"] for counter in counters.values())
    if total != cases:
        raise FuzzError("fuzz accounting mismatch")
    return {
        "format": 1,
        "seed": seed,
        "cases": cases,
        "targets": counters,
        "crashes": 0,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    if path.is_symlink():
        raise FuzzError(f"fuzz report cannot be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--cases", type=int, default=5_000)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=DEFAULT_SEED)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    report_path = (
        arguments.report
        if arguments.report.is_absolute()
        else root / arguments.report
    )
    try:
        report = run(root, arguments.cases, arguments.seed)
        write_report(report_path, report)
    except FuzzError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"fuzzed {report['cases']} control-document mutations across "
        f"{len(report['targets'])} validators with zero crashes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
