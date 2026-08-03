from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_release_channels.py"
SPEC = importlib.util.spec_from_file_location("verify_release_channels", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REVISION = "0123456789abcdef0123456789abcdef01234567"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return digest(content)


def evidence(kind: str, path: str, sha256: str) -> dict:
    return {
        "kind": kind,
        "path": path,
        "sha256": sha256,
        "captured_at": "2026-08-03T14:00:00Z",
        "revision": REVISION,
        "environment": "release-operations",
    }


def readiness(root: Path) -> None:
    document = json.loads((ROOT / "production/readiness.json").read_text(encoding="utf-8"))
    for gate in document["gates"]:
        gate["status"] = "qualified"
    path = root / "production/readiness.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def release_record(root: Path, channel: str = "development") -> dict:
    evidence_root = f"production/evidence/release-operations/{channel}"
    lock_path = f"{evidence_root}/components.lock.toml"
    lock = (
        "format = 1\n"
        "distribution = \"ArachOS\"\n\n"
        "[[component]]\n"
        "name = \"arach-kernel\"\n"
        "repository = \"https://github.com/SisyphusAeolides/Arach-Kernel.git\"\n"
        f"revision = \"{REVISION}\"\n"
        "role = \"kernel\"\n"
    ).encode("utf-8")
    components_lock_sha256 = write(root, lock_path, lock)
    record = {
        "channel": channel,
        "sequence": 1,
        "version": "1.0.0",
        "published_at": "2026-08-03T15:00:00Z",
        "revision": REVISION,
        "components_lock_sha256": components_lock_sha256,
        "package_generation_sha256": digest(b"package generation"),
        "image_sha256": digest(b"image"),
        "signature_sha256": digest(b"signature"),
        "promoted_from_sequence": None,
        "soak_seconds": 0,
        "mirror_count": 2,
        "rollback_tested": True,
        "advisory": f"docs/advisories/{channel}-1.0.0.md",
        "evidence": [],
    }
    write(root, record["advisory"], b"Release notes and rollback instructions.\n")
    report_path = f"{evidence_root}/release-report.json"
    report = {
        "format": 1,
        "distribution": "ArachOS",
        "revision": record["revision"],
        "components_lock": lock_path,
        "components_lock_sha256": record["components_lock_sha256"],
        "package_generation_sha256": record["package_generation_sha256"],
        "image_sha256": record["image_sha256"],
        "signature_sha256": record["signature_sha256"],
    }
    record["evidence"] = [
        evidence("release-report", report_path, write(root, report_path, json.dumps(report).encode("utf-8"))),
        evidence("test-report", f"{evidence_root}/test-report.txt", write(root, f"{evidence_root}/test-report.txt", b"passed\n")),
    ]
    return record


def policy() -> dict:
    return json.loads((ROOT / "production/release-channels.json").read_text(encoding="utf-8"))


class ReleaseChannelTests(unittest.TestCase):
    def test_hash_bound_development_release_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness(root)
            document = policy()
            document["active_releases"] = [release_record(root)]
            self.assertEqual(MODULE.validate(root, document)["development"], 1)

    def test_placeholder_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness(root)
            document = policy()
            record = release_record(root)
            artifact = record["evidence"][1]
            artifact["sha256"] = write(root, artifact["path"], b"synthetic artifact\n")
            document["active_releases"] = [record]
            with self.assertRaisesRegex(MODULE.ReleasePolicyError, "placeholder evidence"):
                MODULE.validate(root, document)

    def test_promotion_retains_every_immutable_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness(root)
            document = policy()
            development = release_record(root)
            testing = release_record(root, "testing")
            testing["published_at"] = "2026-08-03T16:00:00Z"
            testing["soak_seconds"] = 86_400
            testing["promoted_from_sequence"] = 1
            testing["image_sha256"] = digest(b"different image")
            report_entry = testing["evidence"][0]
            report = json.loads((root / report_entry["path"]).read_text(encoding="utf-8"))
            report["image_sha256"] = testing["image_sha256"]
            report_entry["sha256"] = write(root, report_entry["path"], json.dumps(report).encode("utf-8"))
            for kind in ("security-report", "hardware-report", "reproducibility-report"):
                path = f"production/evidence/release-operations/testing/{kind}.txt"
                testing["evidence"].append(evidence(kind, path, write(root, path, b"passed\n")))
            document["active_releases"] = [development, testing]
            with self.assertRaisesRegex(MODULE.ReleasePolicyError, "retain immutable image_sha256"):
                MODULE.validate(root, document)

    def test_release_report_binds_the_component_lock_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness(root)
            document = policy()
            record = release_record(root)
            report_entry = record["evidence"][0]
            report = json.loads((root / report_entry["path"]).read_text(encoding="utf-8"))
            report["components_lock_sha256"] = digest(b"different lock")
            report_entry["sha256"] = write(root, report_entry["path"], json.dumps(report).encode("utf-8"))
            document["active_releases"] = [record]
            with self.assertRaisesRegex(MODULE.ReleasePolicyError, "components_lock_sha256 differs"):
                MODULE.validate(root, document)


if __name__ == "__main__":
    unittest.main()
