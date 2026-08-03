from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_marker_sequence", ROOT / "scripts" / "verify_marker_sequence.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MarkerSequenceTests(unittest.TestCase):
    def test_writes_hash_bound_lifecycle_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "serial.log"
            log.write_text("boot\nlogin\nshutdown\n", encoding="utf-8")
            matches = MODULE.verify_sequence(log.read_text(encoding="utf-8").splitlines(), ["boot", "login", "shutdown"])
            evidence = root / "evidence.json"
            revision = "0123456789abcdef0123456789abcdef01234567"
            MODULE.write_evidence(evidence, log, matches, revision, "qemu")
            document = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(document["revision"], revision)
            self.assertEqual(document["serial_log_sha256"], hashlib.sha256(log.read_bytes()).hexdigest())
            self.assertEqual([marker["line_number"] for marker in document["markers"]], [1, 2, 3])

    def test_rejects_placeholder_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "serial.log"
            log.write_text("boot\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.MarkerSequenceError, "placeholder"):
                MODULE.write_evidence(root / "evidence.json", log, [], "a" * 40, "qemu")


if __name__ == "__main__":
    unittest.main()
