#!/usr/bin/env python3
import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_components", ROOT / "scripts/verify-components.py"
)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class ComponentLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.components = VERIFY.load_lock(ROOT / "components.lock.toml")

    def test_current_lock_is_complete(self) -> None:
        VERIFY.validate(self.components)

    def test_duplicate_component_is_rejected(self) -> None:
        components = copy.deepcopy(self.components)
        components.append(copy.deepcopy(components[0]))
        with self.assertRaisesRegex(ValueError, "duplicate component"):
            VERIFY.validate(components)

    def test_symbolic_revision_is_rejected(self) -> None:
        components = copy.deepcopy(self.components)
        components[0]["revision"] = "main"
        with self.assertRaisesRegex(ValueError, "full object ID"):
            VERIFY.validate(components)

    def test_missing_component_is_rejected(self) -> None:
        components = copy.deepcopy(self.components[:-1])
        with self.assertRaisesRegex(ValueError, "component set differs"):
            VERIFY.validate(components)


if __name__ == "__main__":
    unittest.main()
