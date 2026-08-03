#!/usr/bin/env python3
"""Verify an ordered sequence of regular-expression markers in a serial log."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


class MarkerSequenceError(ValueError):
    pass


@dataclass(frozen=True)
class MarkerMatch:
    pattern: str
    line_number: int


def load_lines(path: Path) -> list[str]:
    if path.is_symlink() or not path.is_file():
        raise MarkerSequenceError(f"serial log is not a regular file: {path}")
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        raise MarkerSequenceError(f"cannot read serial log {path}: {error}") from error


def verify_sequence(lines: list[str], patterns: list[str]) -> list[MarkerMatch]:
    if not patterns:
        raise MarkerSequenceError("at least one marker is required")

    compiled: list[tuple[str, re.Pattern[str]]] = []
    for pattern in patterns:
        if not pattern:
            raise MarkerSequenceError("markers cannot be empty")
        try:
            compiled.append((pattern, re.compile(pattern)))
        except re.error as error:
            raise MarkerSequenceError(f"invalid marker expression {pattern!r}: {error}") from error

    cursor = 0
    matches: list[MarkerMatch] = []
    for pattern, expression in compiled:
        for index in range(cursor, len(lines)):
            if expression.search(lines[index]) is not None:
                matches.append(MarkerMatch(pattern=pattern, line_number=index + 1))
                cursor = index + 1
                break
        else:
            raise MarkerSequenceError(
                f"serial evidence missing after line {cursor}: {pattern}"
            )
    return matches


def tsv_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def write_report(path: Path, matches: list[MarkerMatch]) -> None:
    if path.is_symlink():
        raise MarkerSequenceError(f"marker report cannot be a symlink: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = ["marker\tline_number"]
        body.extend(f"{tsv_escape(match.pattern)}\t{match.line_number}" for match in matches)
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
    except OSError as error:
        raise MarkerSequenceError(f"cannot write marker report {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--marker", action="append", dest="markers", default=[])
    arguments = parser.parse_args()

    try:
        matches = verify_sequence(load_lines(arguments.log), arguments.markers)
        if arguments.report is not None:
            write_report(arguments.report, matches)
    except MarkerSequenceError as error:
        print(error, file=sys.stderr)
        return 1

    print(f"verified {len(matches)} ordered serial markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
