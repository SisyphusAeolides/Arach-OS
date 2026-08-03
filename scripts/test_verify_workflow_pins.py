#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_workflow_pins", ROOT / "scripts/verify-workflow-pins.py"
)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class WorkflowPinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.locked = VERIFY.load_lock(ROOT / "components.lock.toml")
        self.workflow = (ROOT / ".github/workflows/foundation.yml").read_text(
            encoding="utf-8"
        )

    def test_current_workflow_matches_component_lock(self) -> None:
        VERIFY.validate(self.locked, self.workflow)

    def test_stale_checkout_is_rejected(self) -> None:
        current = self.locked["push"]
        stale = "0" * 40
        altered = self.workflow.replace(f"ref: {current}", f"ref: {stale}", 1)
        with self.assertRaisesRegex(
            VERIFY.WorkflowPinError,
            "Push checkout revision differs",
        ):
            VERIFY.validate(self.locked, altered)

    def test_stale_assertion_is_rejected(self) -> None:
        current = self.locked["granite"]
        stale = "0" * 40
        needle = f"= {current}"
        altered = self.workflow.replace(needle, f"= {stale}", 1)
        with self.assertRaisesRegex(
            VERIFY.WorkflowPinError,
            "Granite revision assertion differs",
        ):
            VERIFY.validate(self.locked, altered)

    def test_duplicate_checkout_is_rejected(self) -> None:
        repository, path = VERIFY.CHECKOUTS["arach-kernel"]
        block = f"""
      - uses: actions/checkout@v7
        with:
          repository: SisyphusAeolides/{repository}
          ref: {self.locked['arach-kernel']}
          path: {path}
"""
        with self.assertRaisesRegex(
            VERIFY.WorkflowPinError,
            "exactly one pinned checkout",
        ):
            VERIFY.validate(self.locked, self.workflow + block)

    def test_symbolic_workflow_ref_is_rejected(self) -> None:
        current = self.locked["arach-kernel"]
        altered = self.workflow.replace(f"ref: {current}", "ref: main", 1)
        with self.assertRaisesRegex(
            VERIFY.WorkflowPinError,
            "exactly one pinned checkout",
        ):
            VERIFY.validate(self.locked, altered)


if __name__ == "__main__":
    unittest.main()
