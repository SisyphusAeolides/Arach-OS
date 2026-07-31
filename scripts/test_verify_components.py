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

    def test_rust_dependency_revisions_follow_component_lock(self) -> None:
        VERIFY.validate_rust_pins(self.components, ROOT / "Cargo.toml")

    def test_stale_hwd_dependency_is_rejected(self) -> None:
        components = copy.deepcopy(self.components)
        next(component for component in components if component["name"] == "arach-hwd")[
            "revision"
        ] = "0" * 40
        with self.assertRaisesRegex(ValueError, "arach-hwd revision differs"):
            VERIFY.validate_rust_pins(components, ROOT / "Cargo.toml")


if __name__ == "__main__":
    unittest.main()
