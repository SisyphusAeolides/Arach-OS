#!/usr/bin/env python3
import gettext
import os
from pathlib import Path
import re
import stat
import subprocess

import libcalamares

from repository import (
    CatalogRepositoryError,
    OFFLINE_CATALOG_ROOT,
    catalog_paths,
    load_repository_configuration,
    remap_catalog_file,
)


_ = gettext.translation(
    "calamares-python",
    localedir=libcalamares.utils.gettext_path(),
    languages=libcalamares.utils.gettext_languages(),
    fallback=True,
).gettext


def pretty_name():
    return _("Verify hardware drivers")


def pretty_status_message():
    return _("Checking hardware driver and firmware coverage")


def run():
    configuration = libcalamares.job.configuration
    executable = configuration.get("executable")
    catalog_sync_executable = configuration.get("catalogSyncExecutable")
    repository_configuration = configuration.get("repositoryConfiguration")
    remote_catalog_root = configuration.get("remoteCatalogRoot")
    sysfs = configuration.get("sysfs")
    modules_alias = configuration.get("modulesAlias")
    modules_firmware = configuration.get("modulesFirmware")
    modules_dep = configuration.get("modulesDep")
    modules_builtin = configuration.get("modulesBuiltin")
    firmware_roots = configuration.get("firmwareRoots")
    report = configuration.get("report")
    profiles = configuration.get("profiles")
    keyring = configuration.get("keyring")
    catalog_lock = configuration.get("catalogLock")
    driver_abi_path = configuration.get("driverAbi")
    binary_index = configuration.get("binaryIndex")
    binary_signature = configuration.get("binarySignature")
    plan = configuration.get("plan")
    require_target_profiles = configuration.get("requireTargetProfiles")
    if (
        executable != "/system/arach-hwd"
        or catalog_sync_executable != "/system/arach-hwd-catalog-sync"
        or repository_configuration != "/etc/arach/hwd/repository.toml"
        or remote_catalog_root != "/run/arach-installer/catalog"
        or sysfs != "/sys"
        or not isinstance(modules_alias, list)
        or not isinstance(modules_firmware, list)
        or not isinstance(modules_dep, list)
        or not isinstance(modules_builtin, list)
        or not isinstance(firmware_roots, list)
        or report != "/run/arach-installer/hardware.toml"
        or profiles != "/etc/arach/hwd/profiles"
        or keyring != "/etc/arach/hwd/keys.toml"
        or catalog_lock != "/etc/arach/hwd/catalog.lock"
        or driver_abi_path != "/etc/arach/hwd/driver-abi"
        or binary_index != "/etc/arach/hwd/packages.toml"
        or binary_signature != "/etc/arach/hwd/packages.toml.sig"
        or plan != "/run/arach-installer/hardware.plan.toml"
        or require_target_profiles is not True
    ):
        return (
            _("Invalid hardware preflight configuration"),
            _("Required paths are absent"),
        )
    try:
        report_parent = Path(report).parent
        report_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        return (_("Hardware preflight failed"), str(error))

    try:
        repository = load_repository_configuration(Path(repository_configuration))
        active_catalog = catalog_paths(OFFLINE_CATALOG_ROOT)
    except CatalogRepositoryError as error:
        return (_("Hardware repository configuration is invalid"), str(error))

    sync_error = None
    if repository is not None:
        sync_path = Path(catalog_sync_executable)
        bootstrap_keyring = repository.keyring
        try:
            sync_metadata = sync_path.lstat()
            keyring_metadata = bootstrap_keyring.lstat()
            if (
                stat.S_ISLNK(sync_metadata.st_mode)
                or not stat.S_ISREG(sync_metadata.st_mode)
                or not os.access(sync_path, os.X_OK)
                or stat.S_ISLNK(keyring_metadata.st_mode)
                or not stat.S_ISREG(keyring_metadata.st_mode)
            ):
                raise OSError(
                    "catalog sync executable or bootstrap keyring is not a trusted regular file"
                )
            remote_paths = catalog_paths(Path(remote_catalog_root))
            if remote_paths.root.exists():
                remote_metadata = remote_paths.root.lstat()
                if stat.S_ISLNK(remote_metadata.st_mode) or not stat.S_ISDIR(
                    remote_metadata.st_mode
                ):
                    raise OSError("remote catalog output is not a real directory")
            else:
                result = subprocess.run(
                    [
                        catalog_sync_executable,
                        "--manifest-url",
                        repository.manifest_url,
                        "--signature-url",
                        repository.signature_url,
                        "--keyring",
                        str(repository.keyring),
                        "--output",
                        str(remote_paths.root),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode != 0:
                    detail = (
                        result.stderr or result.stdout or "no diagnostic"
                    ).strip()
                    raise OSError(f"catalog synchronization failed: {detail}")
            active_catalog = remote_paths
        except (OSError, subprocess.TimeoutExpired) as error:
            sync_error = str(error)
            if repository.required:
                return (_("Remote hardware catalog is unavailable"), sync_error)
            active_catalog = catalog_paths(OFFLINE_CATALOG_ROOT)

    profile_dir = active_catalog.profiles
    keyring_path = active_catalog.keyring
    catalog_path = active_catalog.catalog_lock
    driver_abi_file = active_catalog.driver_abi
    binary_index_path = active_catalog.binary_index
    binary_signature_path = active_catalog.binary_signature
    for required in (
        keyring_path,
        catalog_path,
        driver_abi_file,
        binary_index_path,
        binary_signature_path,
    ):
        try:
            metadata = required.lstat()
        except OSError as error:
            return (_("Hardware catalog is incomplete"), str(error))
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return (
                _("Hardware catalog is incomplete"),
                f"missing regular file: {required}",
            )
    try:
        profile_metadata = profile_dir.lstat()
    except OSError as error:
        return (_("Hardware catalog is incomplete"), str(error))
    if stat.S_ISLNK(profile_metadata.st_mode) or not stat.S_ISDIR(
        profile_metadata.st_mode
    ):
        return (
            _("Hardware catalog is incomplete"),
            f"missing profile directory: {profile_dir}",
        )
    try:
        driver_abi = driver_abi_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        return (_("Hardware catalog is unreadable"), str(error))
    if not re.fullmatch(r"[0-9]+\.[0-9]+", driver_abi):
        return (_("Hardware catalog is invalid"), "driver ABI must be MAJOR.MINOR")

    def metadata_arguments(values, option):
        result = []
        for value in values:
            path = remap_catalog_file(value, active_catalog.root)
            try:
                metadata = path.lstat()
            except OSError as error:
                raise CatalogRepositoryError(str(error)) from error
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise CatalogRepositoryError(
                    f"metadata path is not a regular file: {path}"
                )
            result.extend((option, str(path)))
        return result

    try:
        metadata = metadata_arguments(modules_alias, "--modules-alias")
        metadata.extend(metadata_arguments(modules_firmware, "--modules-firmware"))
        metadata.extend(metadata_arguments(modules_dep, "--modules-dep"))
        metadata.extend(metadata_arguments(modules_builtin, "--modules-builtin"))
        for value in firmware_roots:
            if (
                not isinstance(value, str)
                or not value.startswith("/")
                or "\x00" in value
            ):
                raise CatalogRepositoryError(
                    "--firmware-root entries must be absolute paths"
                )
            path = Path(value)
            path_metadata = path.lstat()
            if stat.S_ISLNK(path_metadata.st_mode) or not stat.S_ISDIR(
                path_metadata.st_mode
            ):
                raise CatalogRepositoryError(
                    f"firmware root is not a real directory: {path}"
                )
            metadata.extend(("--firmware-root", value))
    except (CatalogRepositoryError, OSError) as error:
        return (_("Hardware catalog is invalid"), str(error))

    commands = [
        [
            executable,
            "plan",
            "--sysfs",
            sysfs,
            *metadata,
            "--profiles",
            str(profile_dir),
            "--keyring",
            str(keyring_path),
            "--catalog-lock",
            str(catalog_path),
            "--driver-abi",
            driver_abi,
            "--output",
            plan,
            "--require-target-profiles",
        ],
        [
            executable,
            "preflight",
            "--sysfs",
            sysfs,
            *metadata,
            "--output",
            report,
            "--allow-unresolved",
        ],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return (_("Hardware preflight failed"), str(error))
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no diagnostic").strip()
            return (_("Hardware driver coverage is incomplete"), detail)

    storage = libcalamares.globalstorage
    storage.insert("arachHardwareReport", report)
    storage.insert("arachHardwarePlan", plan)
    storage.insert("arachHardwareCatalogRoot", str(active_catalog.root))
    storage.insert("arachHardwareProfiles", str(profile_dir))
    storage.insert("arachHardwareKeyring", str(keyring_path))
    storage.insert("arachHardwareCatalogLock", str(catalog_path))
    storage.insert("arachHardwareBinaryIndex", str(binary_index_path))
    storage.insert("arachHardwareBinarySignature", str(binary_signature_path))
    storage.insert(
        "arachHardwareCatalogSource",
        "remote" if active_catalog.root != OFFLINE_CATALOG_ROOT else "offline",
    )
    if sync_error is not None:
        storage.insert("arachHardwareCatalogSyncError", sync_error)
    return None
