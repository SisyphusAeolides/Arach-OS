from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_installer_recovery.py"
SPEC = importlib.util.spec_from_file_location("verify_installer_recovery", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pending_manifest() -> dict:
    return {
        "format": 1,
        "distribution": "Arach OS",
        "scenarios": [
            {
                "id": scenario_id,
                "title": title,
                "status": "pending",
                "blocker": "not certified",
                "evidence": [],
            }
            for scenario_id, title in MODULE.SCENARIOS
        ],
    }


def evidence(root: Path, outcome: str = "success", digest_override: str | None = None) -> dict:
    artifact = root / "production" / "evidence" / "installer-recovery" / "clean-install.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"result":"pass"}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "artifact": "production/evidence/installer-recovery/clean-install.json",
        "sha256": digest_override or digest,
        "catalog_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
        "journal_sha256": "c" * 64,
        "captured_at": "2026-08-03T13:00:00Z",
        "revision": "d" * 40,
        "outcome": outcome,
        "post_recovery_boot": True,
        "cosmic_launch": True,
    }


class InstallerRecoveryTests(unittest.TestCase):
    def test_pending_matrix_is_valid_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            counts = MODULE.audit(Path(directory), pending_manifest())
            self.assertEqual(counts, {"pending": 13, "failed": 0, "passed": 0})

    def test_passed_scenario_requires_hash_bound_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = pending_manifest()
            document["scenarios"][0].update(
                status="passed",
                blocker=None,
                evidence=[evidence(root)],
            )
            counts = MODULE.audit(root, document)
            self.assertEqual(counts["passed"], 1)

    def test_digest_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = pending_manifest()
            document["scenarios"][0].update(
                status="passed",
                blocker=None,
                evidence=[evidence(root, digest_override="0" * 64)],
            )
            with self.assertRaisesRegex(MODULE.RecoveryError, "does not match"):
                MODULE.audit(root, document)

    def test_manual_intervention_does_not_qualify_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = pending_manifest()
            document["scenarios"][0].update(
                status="passed",
                blocker=None,
                evidence=[evidence(root, outcome="manual-intervention-required")],
            )
            with self.assertRaisesRegex(MODULE.RecoveryError, "lacks successful boot"):
                MODULE.audit(root, document)

    def test_scenario_order_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            document = pending_manifest()
            document["scenarios"][0], document["scenarios"][1] = (
                document["scenarios"][1],
                document["scenarios"][0],
            )
            with self.assertRaisesRegex(MODULE.RecoveryError, "canonical scenario order"):
                MODULE.audit(Path(directory), document)


if __name__ == "__main__":
    unittest.main()
