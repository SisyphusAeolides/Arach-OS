#!/usr/bin/env python3
import copy
import importlib.util
import pathlib
import unittest
from unittest import mock


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

    def test_corinth_nested_hwd_drift_is_rejected(self) -> None:
        locked = {
            component["name"]: component["revision"] for component in self.components
        }
        manifest = """
[dependencies.arach-hwd]
git = "https://github.com/SisyphusAeolides/Arach-HWD.git"
rev = "0000000000000000000000000000000000000000"
"""
        with mock.patch.object(VERIFY, "show_remote_file", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "different Arach-HWD"):
                VERIFY.validate_nested_authority(
                    {"name": "corinth"}, "/unused", locked
                )

    def test_package_recipe_nested_drift_is_rejected(self) -> None:
        locked = {
            component["name"]: component["revision"] for component in self.components
        }
        documents = {
            "recipes/base/corinth/package.toml": f"""
[[source]]
kind = "git"
url = "https://github.com/SisyphusAeolides/Corinth.git"
revision = "{locked['corinth']}"
""",
            "recipes/base/arach-hwd/package.toml": """
[[source]]
kind = "git"
url = "https://github.com/SisyphusAeolides/Arach-HWD.git"
revision = "0000000000000000000000000000000000000000"
""",
        }

        def document(_directory: str, path: str) -> str:
            return documents[path]

        with mock.patch.object(VERIFY, "show_remote_file", side_effect=document):
            with self.assertRaisesRegex(ValueError, "arach-hwd recipe differs"):
                VERIFY.validate_nested_authority(
                    {"name": "arach-packages"}, "/unused", locked
                )

    def test_package_kernel_recipe_drift_is_rejected(self) -> None:
        locked = {
            component["name"]: component["revision"] for component in self.components
        }
        documents = {
            "recipes/base/corinth/package.toml": f"""
[[source]]
kind = "git"
url = "https://github.com/SisyphusAeolides/Corinth.git"
revision = "{locked['corinth']}"
""",
            "recipes/base/arach-hwd/package.toml": f"""
[[source]]
kind = "git"
url = "https://github.com/SisyphusAeolides/Arach-HWD.git"
revision = "{locked['arach-hwd']}"
""",
            "recipes/base/arach-kernel/package.toml": f"""
[[source]]
kind = "git"
url = "https://github.com/SisyphusAeolides/Arach-Kernel.git"
revision = "{'0' * 40}"
submodules = false

[[source]]
kind = "git"
url = "https://github.com/SisyphusAeolides/Push.git"
revision = "{locked['push']}"
submodules = false
""",
        }

        def document(_directory: str, path: str) -> str:
            return documents[path]

        with mock.patch.object(VERIFY, "show_remote_file", side_effect=document):
            with self.assertRaisesRegex(ValueError, "kernel recipe differs"):
                VERIFY.validate_nested_authority(
                    {"name": "arach-packages"}, "/unused", locked
                )


if __name__ == "__main__":
    unittest.main()
