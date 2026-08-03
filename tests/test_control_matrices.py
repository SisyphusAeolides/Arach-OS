from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_control_matrices.py"
SPEC = importlib.util.spec_from_file_location("verify_control_matrices", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def document(status: str = "pending") -> dict:
    return {
        "format": 1,
        "distribution": "ArachOS",
        "matrix": "test-matrix",
        "title": "Test matrix",
        "controls": [
            {
                "id": "control",
                "title": "Control",
                "status": status,
                "components": ["ArachOS"],
                "required_evidence": ["test-report"],
                "required_environments": ["qemu"],
                "evidence": [],
                "blockers": ["not qualified"],
            }
        ],
    }


def evidence(root: Path, digest_override: str | None = None, environment: str = "qemu") -> dict:
    artifact = root / "production" / "evidence" / "test-matrix" / "report.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"result":"pass"}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "kind": "test-report",
        "path": "production/evidence/test-matrix/report.json",
        "sha256": digest_override or digest,
        "captured_at": "2026-08-03T13:00:00Z",
        "revision": "a" * 40,
        "component": "ArachOS",
        "environment": environment,
    }


class ControlMatrixTests(unittest.TestCase):
    def test_pending_control_is_explicitly_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            counts = MODULE.validate_document(Path(directory), document(), ["control"])
            self.assertEqual(counts["pending"], 1)

    def test_qualified_control_requires_hash_bound_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = document("qualified")
            value["controls"][0]["blockers"] = []
            value["controls"][0]["evidence"] = [evidence(root)]
            counts = MODULE.validate_document(root, value, ["control"])
            self.assertEqual(counts["qualified"], 1)

    def test_qualified_control_requires_every_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = document("qualified")
            value["controls"][0]["blockers"] = []
            value["controls"][0]["required_environments"] = ["qemu", "physical-hardware"]
            value["controls"][0]["evidence"] = [evidence(root)]
            with self.assertRaisesRegex(MODULE.ControlMatrixError, "lacks required environments"):
                MODULE.validate_document(root, value, ["control"])

    def test_artifact_digest_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = document("qualified")
            value["controls"][0]["blockers"] = []
            value["controls"][0]["evidence"] = [evidence(root, digest_override="0" * 64)]
            with self.assertRaisesRegex(MODULE.ControlMatrixError, "does not match"):
                MODULE.validate_document(root, value, ["control"])

    def test_control_order_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MODULE.ControlMatrixError, "canonical control order"):
                MODULE.validate_document(Path(directory), document(), ["different-control"])

    def test_failed_control_requires_retained_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MODULE.ControlMatrixError, "requires blockers and evidence"):
                MODULE.validate_document(Path(directory), document("failed"), ["control"])


if __name__ == "__main__":
    unittest.main()
