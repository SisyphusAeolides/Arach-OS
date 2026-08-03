from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_marker_sequence.py"
SPEC = importlib.util.spec_from_file_location("verify_marker_sequence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MarkerSequenceTests(unittest.TestCase):
    def test_repeated_marker_binds_to_occurrence_after_cursor(self) -> None:
        lines = [
            "service ready",
            "boot start",
            "service ready",
            "desktop ready",
        ]
        matches = MODULE.verify_sequence(
            lines,
            ["boot start", "service ready", "desktop ready"],
        )
        self.assertEqual([match.line_number for match in matches], [2, 3, 4])

    def test_missing_marker_after_cursor_is_rejected(self) -> None:
        lines = ["desktop ready", "boot start"]
        with self.assertRaisesRegex(
            MODULE.MarkerSequenceError,
            "serial evidence missing after line 2",
        ):
            MODULE.verify_sequence(lines, ["boot start", "desktop ready"])

    def test_invalid_expression_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.MarkerSequenceError, "invalid marker expression"):
            MODULE.verify_sequence(["boot"], ["["])

    def test_report_is_canonical_and_escaped(self) -> None:
        matches = [MODULE.MarkerMatch(pattern=r"service\tready", line_number=7)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.tsv"
            MODULE.write_report(path, matches)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "marker\tline_number\nservice\\\\tready\t7\n",
            )

    def test_symlink_log_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "serial.log"
            source.write_text("boot\n", encoding="utf-8")
            link = root / "serial-link.log"
            link.symlink_to(source)
            with self.assertRaisesRegex(MODULE.MarkerSequenceError, "not a regular file"):
                MODULE.load_lines(link)


if __name__ == "__main__":
    unittest.main()
