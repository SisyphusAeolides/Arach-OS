#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from adapter import PacmanAdapterError, SignedSnapshot, SnapshotPackage, pacman_command, parse_signed_snapshot, validate_verified_plan


def digest(value):
    return hashlib.sha256(value).hexdigest()


class PacmanAdapterTests(unittest.TestCase):
    def test_snapshot_requires_explicit_plan_bound_archives(self):
        plan = "a" * 64
        config = "b" * 64
        archive = "c" * 64
        snapshot = parse_signed_snapshot(
            (
                f'format = 1\nplan_sha256 = "{plan}"\n'
                f'pacman_config_sha256 = "{config}"\n\n'
                f'[[package]]\narchive = "signed-driver.pkg.tar.zst"\nsha256 = "{archive}"\n'
            ).encode()
        )
        self.assertEqual(snapshot.plan_sha256, plan)
        self.assertEqual(snapshot.packages[0].archive, "signed-driver.pkg.tar.zst")

    def test_snapshot_rejects_guessed_names_and_unknown_fields(self):
        base = (
            f'format = 1\nplan_sha256 = "{"a" * 64}"\n'
            f'pacman_config_sha256 = "{"b" * 64}"\n\n'
        )
        for package in (
            '[[package]]\narchive = "../guess.pkg.tar.zst"\nsha256 = "' + "c" * 64 + '"\n',
            '[[package]]\narchive = "guess.pkg.tar.zst"\nsha256 = "' + "c" * 64 + '"\nname = "guessed"\n',
        ):
            with self.subTest(package=package):
                with self.assertRaises(PacmanAdapterError):
                    parse_signed_snapshot((base + package).encode())

    def test_receipt_binds_exact_plan_and_catalog(self):
        plan = b"schema = 2\nplan = []\n"
        catalog = b"catalog lock\n"
        receipt = {
            "catalog_lock_sha256": digest(catalog),
            "plan_sha256": digest(plan),
            "schema": 1,
            "verifier": "arach-hwd-plan",
        }
        raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.assertEqual(validate_verified_plan(plan, raw, catalog), digest(plan))
        with self.assertRaises(PacmanAdapterError):
            validate_verified_plan(plan + b"# changed\n", raw, catalog)

    def test_command_uses_only_staged_archives_and_upgrade_mode(self):
        snapshot = SignedSnapshot(
            "a" * 64,
            "b" * 64,
            (SnapshotPackage("verified.pkg.tar.zst", "c" * 64),),
        )
        stage = Path(
            "/run/arach-installer/0123456789abcdef0123456789abcdef/pacman-snapshot"
        )
        # Command construction is pure; filesystem checks belong to execution.
        with mock.patch("adapter._require_target"), mock.patch(
            "adapter._require_real_directory"
        ):
            command = pacman_command(Path("/mnt"), stage, snapshot)
        self.assertEqual(command[0], "/usr/bin/pacman")
        self.assertIn("-U", command)
        self.assertIn(str(stage / "verified.pkg.tar.zst"), command)
        self.assertNotIn("-S", command)


if __name__ == "__main__":
    unittest.main()
