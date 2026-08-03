#!/usr/bin/env python3
"""Bind measured workflow checkouts to the Arach OS component lock."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tomllib


CHECKOUTS = {
    "arach-kernel": ("Arach-Kernel", "target/live-sources/kernel"),
    "push": ("Push", "target/live-sources/push"),
    "granite": ("Granite", "target/live-sources/granite"),
}
REVISION = re.compile(r"^[0-9a-f]{40}$")


class WorkflowPinError(ValueError):
    pass


def load_lock(path: pathlib.Path) -> dict[str, str]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise WorkflowPinError(f"cannot load component lock: {error}") from error
    components = document.get("component")
    if not isinstance(components, list):
        raise WorkflowPinError("component lock has no component array")
    locked: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            raise WorkflowPinError("component lock entry is not a table")
        name = component.get("name")
        revision = component.get("revision")
        if not isinstance(name, str) or not isinstance(revision, str):
            raise WorkflowPinError("component lock entry lacks name or revision")
        if not REVISION.fullmatch(revision):
            raise WorkflowPinError(f"component {name} revision is invalid")
        if name in locked:
            raise WorkflowPinError(f"component {name} is duplicated")
        locked[name] = revision
    return locked


def checkout_revision(workflow: str, repository: str, path: str) -> str:
    expression = re.compile(
        rf"(?m)^\s+repository:\s*SisyphusAeolides/{re.escape(repository)}\s*$"
        rf"\n^\s+ref:\s*([0-9a-f]{{40}})\s*$"
        rf"\n^\s+path:\s*{re.escape(path)}\s*$"
    )
    matches = expression.findall(workflow)
    if len(matches) != 1:
        raise WorkflowPinError(
            f"workflow must contain exactly one pinned checkout for {repository}"
        )
    return matches[0]


def verify_line_revision(workflow: str, path: str) -> str:
    expression = re.compile(
        rf'(?m)^\s*test "\$\(git -C {re.escape(path)} rev-parse HEAD\)" = ([0-9a-f]{{40}})\s*$'
    )
    matches = expression.findall(workflow)
    if len(matches) != 1:
        raise WorkflowPinError(
            f"workflow must contain exactly one revision assertion for {path}"
        )
    return matches[0]


def validate(locked: dict[str, str], workflow: str) -> None:
    for component_name, (repository, path) in CHECKOUTS.items():
        expected = locked.get(component_name)
        if expected is None:
            raise WorkflowPinError(f"component lock lacks {component_name}")
        checkout = checkout_revision(workflow, repository, path)
        assertion = verify_line_revision(workflow, path)
        if checkout != expected:
            raise WorkflowPinError(
                f"{repository} checkout revision differs from components.lock.toml"
            )
        if assertion != expected:
            raise WorkflowPinError(
                f"{repository} revision assertion differs from components.lock.toml"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=pathlib.Path)
    parser.add_argument("--workflow", required=True, type=pathlib.Path)
    arguments = parser.parse_args()
    try:
        locked = load_lock(arguments.lock)
        workflow = arguments.workflow.read_text(encoding="utf-8")
        validate(locked, workflow)
    except (OSError, WorkflowPinError) as error:
        print(error, file=sys.stderr)
        return 1
    print("verified measured workflow component pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
