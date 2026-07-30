import importlib.util
import json
import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("protocol.py")
SPEC = importlib.util.spec_from_file_location("arachtransaction_protocol", MODULE_PATH)
PROTOCOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROTOCOL)


class ProtocolTests(unittest.TestCase):
    def test_state_handoff_is_allowlisted_and_secret_free(self):
        source = {
            "username": "arach",
            "hostname": "arach-host",
            "password": "never-cross",
            "luksPassphrase": "never-cross",
            "unrecognized": "never-cross",
        }
        requested = []

        def value(key):
            requested.append(key)
            return source.get(key)

        state = PROTOCOL.collect_state(value, "0" * 32)
        self.assertEqual(state["username"], "arach")
        self.assertNotIn("password", state)
        self.assertNotIn("luksPassphrase", state)
        self.assertNotIn("unrecognized", state)
        self.assertTrue(set(requested).isdisjoint(PROTOCOL.SECRET_KEYS))

    def test_atomic_json_is_canonical_private_and_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary) / "transaction"
            path = directory / "state.json"
            PROTOCOL.atomic_json(path, {"z": 1, "a": 2})
            self.assertEqual(path.read_text(encoding="utf-8"), '{"a":2,"z":1}\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertFalse(any(item.name.startswith(".state.json.") for item in directory.iterdir()))

    def test_execute_never_uses_a_shell(self):
        with mock.patch.object(PROTOCOL.subprocess, "run") as run:
            PROTOCOL.execute(["/usr/libexec/arach-install", "prepare"])
        run.assert_called_once_with(
            ["/usr/libexec/arach-install", "prepare"], check=True, shell=False
        )

    def test_execute_rejects_string_commands(self):
        with self.assertRaises(PROTOCOL.TransactionFailure):
            PROTOCOL.execute("arach-install prepare")

    def test_transaction_paths_remain_below_the_runtime_directory(self):
        transaction_id = PROTOCOL.new_transaction_id()
        self.assertRegex(transaction_id, r"^[0-9a-f]{32}$")
        paths = PROTOCOL.paths("/run/arach-installer", transaction_id)
        expected = pathlib.Path("/run/arach-installer") / transaction_id
        self.assertEqual(paths["base"], expected)
        self.assertEqual(paths["journal"], expected / "journal.json")


if __name__ == "__main__":
    unittest.main()
