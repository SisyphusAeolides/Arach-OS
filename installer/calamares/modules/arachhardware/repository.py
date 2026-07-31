#!/usr/bin/env python3
from dataclasses import dataclass
from pathlib import Path
import stat
import tomllib
from urllib.parse import urlsplit


MAX_REPOSITORY_CONFIGURATION_BYTES = 64 * 1024
REPOSITORY_CONFIGURATION_FORMAT = 1
OFFLINE_CATALOG_ROOT = Path("/etc/arach/hwd")
REPOSITORY_KEYRING = OFFLINE_CATALOG_ROOT / "keys.toml"


class CatalogRepositoryError(ValueError):
    pass


@dataclass(frozen=True)
class RepositoryConfiguration:
    manifest_url: str
    signature_url: str
    keyring: Path
    required: bool


@dataclass(frozen=True)
class CatalogPaths:
    root: Path
    profiles: Path
    keyring: Path
    catalog_lock: Path
    driver_abi: Path
    binary_index: Path
    binary_signature: Path


def load_repository_configuration(path: Path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CatalogRepositoryError(str(error)) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size == 0
        or metadata.st_size > MAX_REPOSITORY_CONFIGURATION_BYTES
    ):
        raise CatalogRepositoryError(
            "hardware repository configuration must be a bounded regular file"
        )
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        document = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise CatalogRepositoryError(
            "hardware repository configuration is unreadable"
        ) from error
    expected = {
        "format",
        "manifest_url",
        "signature_url",
        "keyring",
        "required",
    }
    if set(document) != expected:
        raise CatalogRepositoryError(
            "hardware repository configuration has unknown or missing fields"
        )
    if document["format"] != REPOSITORY_CONFIGURATION_FORMAT:
        raise CatalogRepositoryError("unsupported hardware repository format")
    if not isinstance(document["required"], bool):
        raise CatalogRepositoryError("hardware repository required flag must be Boolean")
    manifest_url = _https_url(document["manifest_url"], "manifest_url")
    signature_url = _https_url(document["signature_url"], "signature_url")
    keyring = document["keyring"]
    if not isinstance(keyring, str) or Path(keyring) != REPOSITORY_KEYRING:
        raise CatalogRepositoryError(
            "hardware repository keyring must use the measured bootstrap path"
        )
    return RepositoryConfiguration(
        manifest_url=manifest_url,
        signature_url=signature_url,
        keyring=Path(keyring),
        required=document["required"],
    )


def catalog_paths(root: Path):
    if not root.is_absolute() or root == Path("/"):
        raise CatalogRepositoryError("hardware catalog root must be absolute and non-root")
    return CatalogPaths(
        root=root,
        profiles=root / "profiles",
        keyring=root / "keys.toml",
        catalog_lock=root / "catalog.lock",
        driver_abi=root / "driver-abi",
        binary_index=root / "packages.toml",
        binary_signature=root / "packages.toml.sig",
    )


def remap_catalog_file(value: str, active_root: Path):
    if not isinstance(value, str) or "\x00" in value:
        raise CatalogRepositoryError("catalog metadata path is invalid")
    path = Path(value)
    try:
        relative = path.relative_to(OFFLINE_CATALOG_ROOT)
    except ValueError as error:
        raise CatalogRepositoryError(
            "catalog metadata path is outside the measured catalog root"
        ) from error
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise CatalogRepositoryError("catalog metadata path is not canonical")
    return active_root / relative


def _https_url(value, field):
    if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
        raise CatalogRepositoryError(f"hardware repository {field} is invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path
    ):
        raise CatalogRepositoryError(
            f"hardware repository {field} must be an HTTPS URL without credentials or fragments"
        )
    return value
