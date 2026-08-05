from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_archiso_qualification.py"
SPEC = importlib.util.spec_from_file_location("verify_archiso_qualification", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REVISION = "0" * 40
FINGERPRINT = "A" * 40


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return digest(content)


def signed(root: Path, relative: str, content: bytes) -> dict[str, str]:
    return {
        "path": relative,
        "sha256": write(root, relative, content),
        "signature": f"{relative}.sig",
        "signature_sha256": write(root, f"{relative}.sig", b"detached signature\n"),
        "signer_fingerprint": FINGERPRINT,
    }


def package_lock(root: Path) -> dict:
    database = signed(root, "sources/core.db", b"immutable snapshot database\n")
    repository = "https://packages.example.invalid/snapshots/20260805.1"
    packages = [
        {
            "name": name,
            "version": "1.0-1",
            "architecture": "x86_64",
            "repository": repository,
            "archive": signed(
                root,
                f"packages/{name}-1.0-1-x86_64.pkg.tar.zst",
                f"{name} package\n".encode(),
            ),
        }
        for name in sorted(MODULE.REQUIRED_CHOICE_PACKAGES)
    ]
    package_set = MODULE.canonical_sha256(packages)
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "packages": [
            {"name": package["name"], "versionInfo": package["version"]}
            for package in packages
        ],
    }
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {},
        "subject": [
            {
                "name": "arachos-package-set",
                "digest": {"sha256": package_set},
            }
        ],
    }
    return {
        "format": 1,
        "distribution": "ArachOS",
        "archiso_profile_revision": REVISION,
        "snapshot": {
            "id": "20260805.1",
            "repository": repository,
            "generated_at": "2026-08-05T18:00:00Z",
            "database": database,
            "keyring": {
                "path": "keys/archiso.gpg",
                "sha256": write(root, "keys/archiso.gpg", b"keyring\n"),
            },
            "verification": {
                "path": "verification/snapshot-gpgv.txt",
                "sha256": write(root, "verification/snapshot-gpgv.txt", b"Good signature\n"),
                "tool": "gpgv",
            },
        },
        "packages": packages,
        "package_set_sha256": package_set,
        "sbom": {
            "path": "metadata/sbom.spdx.json",
            "sha256": write(
                root,
                "metadata/sbom.spdx.json",
                (json.dumps(sbom, sort_keys=True) + "\n").encode(),
            ),
            "format": "spdx-json",
            "package_set_sha256": package_set,
        },
        "provenance": {
            "path": "metadata/provenance.intoto.json",
            "sha256": write(
                root,
                "metadata/provenance.intoto.json",
                (json.dumps(provenance, sort_keys=True) + "\n").encode(),
            ),
            "format": "in-toto-statement",
            "package_set_sha256": package_set,
        },
    }


def qemu_report(root: Path, lock: Path, document: dict) -> dict:
    initial = document["snapshot"]["database"]["sha256"]
    updated = digest(b"updated snapshot")
    image_sha256 = write(root, "images/arachos.iso", b"ISO image\n")
    transitions = (
        (initial, initial, False),
        (initial, initial, True),
        (initial, initial, True),
        (initial, updated, True),
        (updated, initial, True),
    )
    scenarios = []
    for scenario_id, (before, after, post_reboot) in zip(MODULE.SCENARIOS, transitions, strict=True):
        log = f"logs/{scenario_id}.log"
        scenarios.append(
            {
                "id": scenario_id,
                "status": "passed",
                "log": log,
                "log_sha256": write(root, log, f"{scenario_id} passed\n".encode()),
                "snapshot_before_sha256": before,
                "snapshot_after_sha256": after,
                "post_reboot": post_reboot,
            }
        )
    return {
        "format": 1,
        "captured_at": "2026-08-05T18:15:00Z",
        "package_lock_sha256": digest(lock.read_bytes()),
        "image": "images/arachos.iso",
        "image_sha256": image_sha256,
        "qemu": {
            "binary": "qemu-system-x86_64",
            "version": "10.0.0",
            "machine": "q35",
            "firmware_sha256": digest(b"OVMF"),
        },
        "firmware": {
            "path": "firmware/OVMF_CODE.fd",
            "sha256": write(root, "firmware/OVMF_CODE.fd", b"OVMF"),
        },
        "initial_snapshot_sha256": initial,
        "update_snapshot_sha256": updated,
        "scenarios": scenarios,
    }


class ArchisoQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(tempfile.mkdtemp(dir=ROOT / "tests", prefix=".archiso-qualification-"))
        self.artifacts = self.workdir / "artifacts"
        self.document = package_lock(self.artifacts)
        self.lock = self.workdir / "archiso-package-lock.json"
        self.lock.write_text(json.dumps(self.document), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.workdir)

    def test_hash_bound_signed_snapshot_sbom_and_provenance_are_valid(self) -> None:
        result = MODULE.validate_package_lock(self.artifacts, self.document)
        self.assertEqual(result["packages"], len(MODULE.REQUIRED_CHOICE_PACKAGES))

    def test_profile_contract_exposes_only_the_supported_choices(self) -> None:
        MODULE.validate_profile_contract(ROOT / "archiso")

    def test_tampered_signed_package_is_rejected(self) -> None:
        package_path = self.artifacts / self.document["packages"][0]["archive"]["path"]
        package_path.write_bytes(b"tampered package\n")
        with self.assertRaisesRegex(MODULE.QualificationError, "archive digest does not match"):
            MODULE.validate_package_lock(self.artifacts, self.document)

    def test_sbom_must_enumerate_the_locked_packages(self) -> None:
        sbom_path = self.artifacts / self.document["sbom"]["path"]
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
        sbom["packages"].pop()
        sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
        self.document["sbom"]["sha256"] = digest(sbom_path.read_bytes())
        with self.assertRaisesRegex(MODULE.QualificationError, "sbom package names and versions"):
            MODULE.validate_package_lock(self.artifacts, self.document)

    def test_cosmic_requires_all_packages_from_the_immutable_snapshot(self) -> None:
        self.document["packages"] = [
            package for package in self.document["packages"] if package["name"] != "cosmic-greeter"
        ]
        self.document["package_set_sha256"] = MODULE.canonical_sha256(self.document["packages"])
        with self.assertRaisesRegex(MODULE.QualificationError, "cosmic-greeter"):
            MODULE.validate_package_lock(self.artifacts, self.document)

    def test_aur_snapshot_is_rejected(self) -> None:
        self.document["snapshot"]["repository"] = "https://aur.archlinux.org"
        for package in self.document["packages"]:
            package["repository"] = "https://aur.archlinux.org"
        self.document["package_set_sha256"] = MODULE.canonical_sha256(self.document["packages"])
        with self.assertRaisesRegex(MODULE.QualificationError, "must not use the AUR"):
            MODULE.validate_package_lock(self.artifacts, self.document)

    def test_qemu_install_reboot_update_and_rollback_transitions_are_valid(self) -> None:
        report = qemu_report(self.artifacts, self.lock, self.document)
        self.assertEqual(
            MODULE.validate_qemu_report(
                self.artifacts,
                report,
                digest(self.lock.read_bytes()),
                self.document["snapshot"]["database"]["sha256"],
            ),
            5,
        )

    def test_qemu_rollback_must_restore_the_initial_snapshot(self) -> None:
        report = qemu_report(self.artifacts, self.lock, self.document)
        report["scenarios"][-1]["snapshot_after_sha256"] = report["update_snapshot_sha256"]
        with self.assertRaisesRegex(MODULE.QualificationError, "invalid snapshot or reboot transition"):
            MODULE.validate_qemu_report(
                self.artifacts,
                report,
                digest(self.lock.read_bytes()),
                self.document["snapshot"]["database"]["sha256"],
            )

    def test_qemu_requires_retained_firmware_evidence(self) -> None:
        report = qemu_report(self.artifacts, self.lock, self.document)
        firmware_path = self.artifacts / report["firmware"]["path"]
        firmware_path.unlink()
        with self.assertRaisesRegex(MODULE.QualificationError, "QEMU firmware is missing"):
            MODULE.validate_qemu_report(
                self.artifacts,
                report,
                digest(self.lock.read_bytes()),
                self.document["snapshot"]["database"]["sha256"],
            )

    def test_cli_labels_qemu_results_as_structural_evidence_only(self) -> None:
        report = qemu_report(self.artifacts, self.lock, self.document)
        report_path = self.workdir / "qemu-qualification.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        output = io.StringIO()
        arguments = [
            str(MODULE_PATH),
            "--package-lock",
            str(self.lock),
            "--artifacts-root",
            str(self.artifacts),
            "--qemu-report",
            str(report_path),
            "--qemu-artifacts-root",
            str(self.artifacts),
        ]
        with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(output):
            self.assertEqual(MODULE.main(), 0)
        self.assertIn("retained QEMU evidence", output.getvalue())
        self.assertIn("not a claim of real QEMU or hardware qualification", output.getvalue())

    def test_profile_rejects_disabled_hardware_payload_adapter(self) -> None:
        profile = self.workdir / "archiso"
        shutil.copytree(ROOT / "archiso", profile)
        adapter = profile / "calamares/modules/arach-pacman.conf"
        adapter.write_text("---\nenabled: false\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.QualificationError, "explicitly enabled"):
            MODULE.validate_profile_contract(profile)

    def test_profile_rejects_unqualified_bootloader_choice(self) -> None:
        profile = self.workdir / "archiso"
        shutil.copytree(ROOT / "archiso", profile)
        choices = profile / "calamares/modules/bootloader-choice.conf"
        choices.write_text(
            choices.read_text(encoding="utf-8")
            + '\n  - id: limine\n    name: "Limine"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.QualificationError, "bootloader choices"):
            MODULE.validate_profile_contract(profile)


if __name__ == "__main__":
    unittest.main()
