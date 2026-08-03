from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fuzz_control_documents.py"
SPEC = importlib.util.spec_from_file_location("fuzz_control_documents", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ControlFuzzerTests(unittest.TestCase):
    def test_fixed_seed_is_deterministic(self) -> None:
        first = MODULE.run(ROOT, 240, 0xA2AC0DE2026)
        second = MODULE.run(ROOT, 240, 0xA2AC0DE2026)
        self.assertEqual(first, second)
        self.assertEqual(first["crashes"], 0)
        self.assertEqual(first["cases"], 240)
        self.assertEqual(
            sum(target["cases"] for target in first["targets"].values()),
            240,
        )

    def test_every_validator_receives_cases(self) -> None:
        report = MODULE.run(ROOT, 60, 7)
        self.assertGreaterEqual(len(report["targets"]), 6)
        self.assertTrue(
            all(target["cases"] > 0 for target in report["targets"].values())
        )

    def test_case_bounds_are_enforced(self) -> None:
        with self.assertRaisesRegex(MODULE.FuzzError, "between 1 and 100000"):
            MODULE.run(ROOT, 0, 1)
        with self.assertRaisesRegex(MODULE.FuzzError, "between 1 and 100000"):
            MODULE.run(ROOT, 100_001, 1)

    def test_report_is_canonical_json(self) -> None:
        report = MODULE.run(ROOT, 24, 9)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            MODULE.write_report(path, report)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertIn('"crashes": 0', text)
            self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_report_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            link = root / "report.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(MODULE.FuzzError, "cannot be a symlink"):
                MODULE.write_report(link, {"format": 1})


if __name__ == "__main__":
    unittest.main()
