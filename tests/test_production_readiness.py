from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_production_readiness", ROOT / "scripts" / "verify_production_readiness.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProductionReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ROOT / MODULE.MANIFEST_PATH).read_text(encoding="utf-8"))

    def test_repository_manifest_validates(self) -> None:
        MODULE.validate_manifest(ROOT, copy.deepcopy(self.manifest))

    def test_source_truth_includes_release_integrity_promotion(self) -> None:
        self.assertEqual(len(self.manifest["gates"]), 14)
        gate = self.manifest["gates"][-1]
        self.assertEqual(gate["id"], "release-integrity-promotion")
        self.assertEqual(gate["document"], "docs/RELEASE_INTEGRITY_GATE.md")

    def test_release_mode_refuses_unqualified_gates(self) -> None:
        with self.assertRaisesRegex(MODULE.ReadinessError, "production release remains blocked"):
            MODULE.require_production_ready(copy.deepcopy(self.manifest))

    def test_qualified_gate_requires_evidence(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        gate = manifest["gates"][1]
        gate["status"] = "qualified"
        gate["blockers"] = []
        gate["qualified_at"] = "2026-08-03T00:00:00Z"
        gate["qualified_revision"] = "0" * 40
        with self.assertRaisesRegex(MODULE.ReadinessError, "missing required evidence kinds"):
            MODULE.validate_manifest(ROOT, manifest)

    def test_unqualified_gate_requires_a_blocker(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["gates"][0]["blockers"] = []
        with self.assertRaisesRegex(MODULE.ReadinessError, "must state at least one blocker"):
            MODULE.validate_manifest(ROOT, manifest)

    def test_dependency_cycles_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["gates"][1]["depends_on"] = ["cosmic-lifecycle"]
        with self.assertRaisesRegex(MODULE.ReadinessError, "dependency cycle"):
            MODULE.validate_manifest(ROOT, manifest)

    def test_evidence_digest_is_checked(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "production" / "evidence").mkdir(parents=True)
            for gate in manifest["gates"]:
                source = ROOT / gate["document"]
                destination = root / gate["document"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            (root / MODULE.TRACKER_PATH).write_bytes((ROOT / MODULE.TRACKER_PATH).read_bytes())
            evidence = root / "production" / "evidence" / "probe.txt"
            evidence.write_text("measured\n", encoding="utf-8")
            gate = manifest["gates"][1]
            gate["evidence"] = [{
                "kind": "test-report",
                "path": "production/evidence/probe.txt",
                "sha256": "0" * 64,
                "captured_at": "2026-08-03T00:00:00Z",
                "component": "Arach-Kernel",
                "revision": "0" * 40,
            }]
            with self.assertRaisesRegex(MODULE.ReadinessError, "does not match"):
                MODULE.validate_manifest(root, manifest)

    def test_gate_document_status_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            for gate in self.manifest["gates"]:
                source = ROOT / gate["document"]
                destination = root / gate["document"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            tracker = root / MODULE.TRACKER_PATH
            tracker.parent.mkdir(parents=True, exist_ok=True)
            tracker.write_bytes((ROOT / MODULE.TRACKER_PATH).read_bytes())
            gate = self.manifest["gates"][0]
            path = root / gate["document"]
            path.write_text(
                path.read_text(encoding="utf-8").replace("`in_progress`", "`qualified`", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.ReadinessError, "current status does not match"):
                MODULE.validate_manifest(root, copy.deepcopy(self.manifest))

    def test_placeholder_provenance_is_detected(self) -> None:
        self.assertTrue(MODULE.is_placeholder_revision("d" * 40))
        self.assertFalse(MODULE.is_placeholder_revision("0123456789abcdef0123456789abcdef01234567"))
        self.assertTrue(MODULE.is_mock_evidence("production/evidence/security/mock_report.txt"))
        self.assertFalse(MODULE.is_mock_evidence("production/evidence/security/report.txt"))
        self.assertTrue(MODULE.PLACEHOLDER_EVIDENCE_RE.search(b"synthetic evidence"))


if __name__ == "__main__":
    unittest.main()
