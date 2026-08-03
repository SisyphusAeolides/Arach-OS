from __future__ import annotations

import copy
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_threat_model.py"
SPEC = importlib.util.spec_from_file_location("verify_threat_model", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ThreatModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = MODULE.load_model(ROOT)

    def test_current_model_is_structurally_valid(self) -> None:
        counts = MODULE.validate(ROOT, self.model)
        self.assertEqual(sum(counts.values()), 12)
        self.assertEqual(counts["mitigated"], 0)

    def test_unknown_asset_reference_is_rejected(self) -> None:
        model = copy.deepcopy(self.model)
        model["threats"][0]["assets"] = ["unknown-asset"]
        with self.assertRaisesRegex(MODULE.ThreatModelError, "unknown asset"):
            MODULE.validate(ROOT, model)

    def test_missing_control_file_is_rejected(self) -> None:
        model = copy.deepcopy(self.model)
        model["threats"][0]["controls"] = ["missing-control.toml"]
        with self.assertRaisesRegex(MODULE.ThreatModelError, "controls is missing"):
            MODULE.validate(ROOT, model)

    def test_premature_mitigation_is_rejected(self) -> None:
        model = copy.deepcopy(self.model)
        threat = model["threats"][0]
        threat["status"] = "mitigated"
        threat["blockers"] = []
        threat["residual_risk"] = None
        with self.assertRaisesRegex(MODULE.ThreatModelError, "lacks required kinds"):
            MODULE.validate(ROOT, model)

    def test_threat_order_is_canonical(self) -> None:
        model = copy.deepcopy(self.model)
        model["threats"][0], model["threats"][1] = (
            model["threats"][1],
            model["threats"][0],
        )
        with self.assertRaisesRegex(MODULE.ThreatModelError, "canonical threat order"):
            MODULE.validate(ROOT, model)

    def test_hash_bound_evidence_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = copy.deepcopy(self.model)
            for threat in model["threats"]:
                for control in threat["controls"]:
                    path = root / control
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch(exist_ok=True)
            artifact = root / "production/evidence/security/report.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('{"result":"pass"}\n', encoding="utf-8")
            model["threats"][0]["evidence"] = [
                {
                    "kind": "attestation",
                    "path": "production/evidence/security/report.json",
                    "sha256": "0" * 64,
                    "captured_at": "2026-08-03T13:00:00Z",
                    "revision": "a" * 40,
                    "component": "Arach-OS",
                    "environment": "continuous-integration",
                }
            ]
            with self.assertRaisesRegex(MODULE.ThreatModelError, "does not match"):
                MODULE.validate(root, model)

    def test_valid_retained_evidence_can_support_partial_mitigation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = copy.deepcopy(self.model)
            for threat in model["threats"]:
                for control in threat["controls"]:
                    path = root / control
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch(exist_ok=True)
            artifact = root / "production/evidence/security/report.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('{"result":"pass"}\n', encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            model["threats"][0]["evidence"] = [
                {
                    "kind": "attestation",
                    "path": "production/evidence/security/report.json",
                    "sha256": digest,
                    "captured_at": "2026-08-03T13:00:00Z",
                    "revision": "a" * 40,
                    "component": "Arach-OS",
                    "environment": "continuous-integration",
                }
            ]
            counts = MODULE.validate(root, model)
            self.assertEqual(sum(counts.values()), 12)


if __name__ == "__main__":
    unittest.main()
