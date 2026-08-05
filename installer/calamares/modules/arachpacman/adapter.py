#!/usr/bin/env python3
"""Strict signed-snapshot authorization for offline Pacman hardware payloads."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tomllib


FORMAT = 1
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PACKAGES = 256
PLAN_PATH = Path("/run/arach-installer/hardware.plan.toml")
RECEIPT_PATH = Path("/run/arach-installer/hardware.plan.verified.json")
CATALOG_LOCK_PATH = Path("/etc/arach/hwd/catalog.lock")
MAPPING_PATH = Path("/etc/arach/hwd/pacman-snapshot.toml")
SIGNATURE_PATH = Path("/etc/arach/hwd/pacman-snapshot.toml.sig")
KEYRING_PATH = Path("/etc/arach/hwd/pacman-snapshot.gpg")
SNAPSHOT_ROOT = Path("/etc/arach/hwd/pacman-snapshot")
RUNTIME_ROOT = Path("/run/arach-installer")
PACMAN_PATH = Path("/usr/bin/pacman")
GPGV_PATH = Path("/usr/bin/gpgv")


class PacmanAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotPackage:
    archive: str
    sha256: str


@dataclass(frozen=True)
class SignedSnapshot:
    plan_sha256: str
    pacman_config_sha256: str
    packages: tuple[SnapshotPackage, ...]


def parse_signed_snapshot(raw: bytes) -> SignedSnapshot:
    if not raw or len(raw) > MAX_DOCUMENT_BYTES:
        raise PacmanAdapterError("Pacman snapshot is empty or exceeds its size limit")
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PacmanAdapterError("Pacman snapshot is not valid UTF-8 TOML") from error
    if set(document) != {"format", "plan_sha256", "pacman_config_sha256", "package"}:
        raise PacmanAdapterError("Pacman snapshot has unknown or missing fields")
    if document["format"] != FORMAT:
        raise PacmanAdapterError("Pacman snapshot has an unsupported format")
    plan_sha256 = _digest(document["plan_sha256"], "plan_sha256")
    pacman_config_sha256 = _digest(
        document["pacman_config_sha256"], "pacman_config_sha256"
    )
    package_values = document["package"]
    if not isinstance(package_values, list) or len(package_values) > MAX_PACKAGES:
        raise PacmanAdapterError("Pacman snapshot package list is invalid")
    packages = []
    names = set()
    for value in package_values:
        if not isinstance(value, dict) or set(value) != {"archive", "sha256"}:
            raise PacmanAdapterError("Pacman snapshot package has unknown or missing fields")
        archive = _archive_name(value["archive"])
        if archive in names:
            raise PacmanAdapterError("Pacman snapshot contains a duplicate archive")
        names.add(archive)
        packages.append(SnapshotPackage(archive, _digest(value["sha256"], "sha256")))
    return SignedSnapshot(plan_sha256, pacman_config_sha256, tuple(packages))


def validate_verified_plan(plan: bytes, receipt: bytes, catalog_lock: bytes) -> str:
    if not plan or len(plan) > MAX_DOCUMENT_BYTES:
        raise PacmanAdapterError("Arach-HWD plan is empty or exceeds its size limit")
    if not receipt or len(receipt) > MAX_DOCUMENT_BYTES:
        raise PacmanAdapterError("Arach-HWD verification receipt is invalid")
    try:
        text = receipt.decode("utf-8")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PacmanAdapterError("Arach-HWD verification receipt is not JSON") from error
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    if not isinstance(document, dict) or text != canonical or set(document) != {
        "catalog_lock_sha256",
        "plan_sha256",
        "schema",
        "verifier",
    }:
        raise PacmanAdapterError("Arach-HWD verification receipt is not canonical")
    if document["schema"] != FORMAT or document["verifier"] != "arach-hwd-plan":
        raise PacmanAdapterError("Arach-HWD verification receipt has an unsupported format")
    plan_sha256 = _digest(document["plan_sha256"], "plan_sha256")
    catalog_sha256 = _digest(document["catalog_lock_sha256"], "catalog_lock_sha256")
    if plan_sha256 != _sha256(plan):
        raise PacmanAdapterError("Arach-HWD plan differs from its verification receipt")
    if catalog_sha256 != _sha256(catalog_lock):
        raise PacmanAdapterError("Arach-HWD catalog differs from its verification receipt")
    return plan_sha256


def stage_and_authorize(
    transaction_id: str,
    plan_path: Path = PLAN_PATH,
    receipt_path: Path = RECEIPT_PATH,
    catalog_lock_path: Path = CATALOG_LOCK_PATH,
    mapping_path: Path = MAPPING_PATH,
    signature_path: Path = SIGNATURE_PATH,
    keyring_path: Path = KEYRING_PATH,
    snapshot_root: Path = SNAPSHOT_ROOT,
    runtime_root: Path = RUNTIME_ROOT,
) -> tuple[SignedSnapshot, Path]:
    _transaction_id(transaction_id)
    plan = _read_regular(plan_path, MAX_DOCUMENT_BYTES)
    receipt = _read_regular(receipt_path, MAX_DOCUMENT_BYTES)
    catalog_lock = _read_regular(catalog_lock_path, MAX_DOCUMENT_BYTES)
    plan_sha256 = validate_verified_plan(plan, receipt, catalog_lock)
    transaction_root = runtime_root / transaction_id
    _require_private_directory(transaction_root)
    stage = transaction_root / "pacman-snapshot"
    _make_private_directory(stage)
    mapping = _copy_regular(mapping_path, stage / "mapping.toml", MAX_DOCUMENT_BYTES)
    signature = _copy_regular(signature_path, stage / "mapping.toml.sig", MAX_DOCUMENT_BYTES)
    keyring = _copy_regular(keyring_path, stage / "keyring.gpg", MAX_DOCUMENT_BYTES)
    _verify_signature(keyring, signature, mapping)
    snapshot = parse_signed_snapshot(_read_regular(mapping, MAX_DOCUMENT_BYTES))
    if snapshot.plan_sha256 != plan_sha256:
        raise PacmanAdapterError("signed Pacman snapshot is not authorized for this Arach-HWD plan")
    _require_real_directory(snapshot_root)
    config = _copy_regular(
        snapshot_root / "pacman.conf", stage / "pacman.conf", MAX_DOCUMENT_BYTES
    )
    if _sha256(_read_regular(config, MAX_DOCUMENT_BYTES)) != snapshot.pacman_config_sha256:
        raise PacmanAdapterError("Pacman configuration differs from the signed snapshot")
    for package in snapshot.packages:
        _, archive_sha256 = _copy_regular_with_digest(
            snapshot_root / package.archive,
            stage / package.archive,
            MAX_ARCHIVE_BYTES,
        )
        if archive_sha256 != package.sha256:
            raise PacmanAdapterError(
                f"Pacman archive differs from the signed snapshot: {package.archive}"
            )
    return snapshot, stage


def pacman_command(target: Path, stage: Path, snapshot: SignedSnapshot) -> list[str]:
    _require_target(target)
    _require_real_directory(stage)
    if not snapshot.packages:
        raise PacmanAdapterError("empty Pacman snapshots do not authorize execution")
    archives = [str(stage / package.archive) for package in snapshot.packages]
    return [
        str(PACMAN_PATH),
        "--root",
        str(target),
        "--dbpath",
        str(target / "var/lib/pacman"),
        "--cachedir",
        str(stage),
        "--config",
        str(stage / "pacman.conf"),
        "--noconfirm",
        "--needed",
        "-U",
        *archives,
    ]


def execute_pacman(target: Path, snapshot: SignedSnapshot, stage: Path) -> None:
    command = pacman_command(target, stage, snapshot)
    try:
        subprocess.run(command, check=True, shell=False)
    except (OSError, subprocess.CalledProcessError) as error:
        raise PacmanAdapterError(f"authorized Pacman execution failed: {error}") from error


def _read_regular(path: Path, limit: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise PacmanAdapterError(f"{path}: {error}") from error
    try:
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size <= 0
                or metadata.st_size > limit
            ):
                raise PacmanAdapterError(f"{path} is not a bounded regular file")
            value = stream.read(limit + 1)
    except OSError as error:
        raise PacmanAdapterError(f"{path}: {error}") from error
    if len(value) > limit:
        raise PacmanAdapterError(f"{path} exceeds its size limit")
    return value


def _copy_regular(source: Path, destination: Path, limit: int) -> Path:
    copied, _ = _copy_regular_with_digest(source, destination, limit)
    return copied


def _copy_regular_with_digest(source: Path, destination: Path, limit: int) -> tuple[Path, str]:
    try:
        source_descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise PacmanAdapterError(f"cannot read {source}: {error}") from error
    try:
        destination_descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(source_descriptor, "rb") as input_stream, os.fdopen(
            destination_descriptor, "wb"
        ) as output_stream:
            metadata = os.fstat(input_stream.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size <= 0
                or metadata.st_size > limit
            ):
                raise PacmanAdapterError(f"{source} is not a bounded regular file")
            hasher = hashlib.sha256()
            copied = 0
            while chunk := input_stream.read(1024 * 1024):
                copied += len(chunk)
                if copied > limit:
                    raise PacmanAdapterError(f"{source} exceeds its size limit")
                hasher.update(chunk)
                output_stream.write(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    except OSError as error:
        raise PacmanAdapterError(f"cannot stage {source}: {error}") from error
    return destination, hasher.hexdigest()


def _verify_signature(keyring: Path, signature: Path, mapping: Path) -> None:
    try:
        subprocess.run(
            [str(GPGV_PATH), "--keyring", str(keyring), str(signature), str(mapping)],
            check=True,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PacmanAdapterError(f"Pacman snapshot signature verification failed: {error}") from error


def _make_private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except OSError as error:
        raise PacmanAdapterError(f"cannot create Pacman snapshot staging directory: {error}") from error


def _require_real_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PacmanAdapterError(f"{path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PacmanAdapterError(f"{path} is not a real directory")


def _require_private_directory(path: Path) -> None:
    _require_real_directory(path)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise PacmanAdapterError(f"{path} is not a private transaction directory")


def _require_target(path: Path) -> None:
    if not path.is_absolute() or path == Path("/"):
        raise PacmanAdapterError("Pacman target must be an absolute non-root directory")
    _require_real_directory(path)


def _digest(value, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PacmanAdapterError(f"Pacman snapshot {field} must be a SHA-256 digest")
    return value


def _archive_name(value) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in value)
    ):
        raise PacmanAdapterError("Pacman snapshot archive name is invalid")
    return value


def _transaction_id(value) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise PacmanAdapterError("transaction id must be 32 lowercase hexadecimal characters")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
