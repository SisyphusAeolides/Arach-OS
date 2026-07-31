#!/usr/bin/env python3
import gettext
from pathlib import Path
import re
import subprocess

import libcalamares


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
    sysfs = configuration.get("sysfs")
    modules_alias = configuration.get("modulesAlias")
    modules_firmware = configuration.get("modulesFirmware")
    report = configuration.get("report")
    profiles = configuration.get("profiles")
    keyring = configuration.get("keyring")
    catalog_lock = configuration.get("catalogLock")
    driver_abi_path = configuration.get("driverAbi")
    plan = configuration.get("plan")
    require_target_profiles = configuration.get("requireTargetProfiles")
    if (
        executable != "/system/arach-hwd"
        or sysfs != "/sys"
        or not isinstance(modules_alias, list)
        or not isinstance(modules_firmware, list)
        or report != "/run/arach-installer/hardware.toml"
        or profiles != "/etc/arach/hwd/profiles"
        or keyring != "/etc/arach/hwd/keys.toml"
        or catalog_lock != "/etc/arach/hwd/catalog.lock"
        or driver_abi_path != "/etc/arach/hwd/driver-abi"
        or plan != "/run/arach-installer/hardware.plan.toml"
        or require_target_profiles is not True
    ):
        return (_("Invalid hardware preflight configuration"), _("Required paths are absent"))
    try:
        report_parent = Path(report).parent
        report_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        return (_("Hardware preflight failed"), str(error))
    profile_dir = Path(profiles)
    keyring_path = Path(keyring)
    catalog_path = Path(catalog_lock)
    driver_abi_file = Path(driver_abi_path)
    for required in (keyring_path, catalog_path, driver_abi_file):
        if not required.is_file() or required.is_symlink():
            return (_("Hardware catalog is incomplete"), f"missing regular file: {required}")
    if not profile_dir.is_dir() or profile_dir.is_symlink():
        return (_("Hardware catalog is incomplete"), f"missing profile directory: {profile_dir}")
    try:
        driver_abi = driver_abi_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        return (_("Hardware catalog is unreadable"), str(error))
    if not re.fullmatch(r"[0-9]+\.[0-9]+", driver_abi):
        return (_("Hardware catalog is invalid"), "driver ABI must be MAJOR.MINOR")

    def metadata_arguments(values, option):
        result = []
        for value in values:
            if (
                not isinstance(value, str)
                or not value.startswith("/")
                or "\x00" in value
            ):
                raise ValueError(f"{option} entries must be absolute paths")
            path = Path(value)
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"metadata path is not a regular file: {path}")
            result.extend((option, value))
        return result

    try:
        metadata = metadata_arguments(modules_alias, "--modules-alias")
        metadata.extend(metadata_arguments(modules_firmware, "--modules-firmware"))
    except ValueError as error:
        return (_("Hardware catalog is invalid"), str(error))

    commands = [
        [
            executable,
            "preflight",
            "--sysfs",
            sysfs,
            *metadata,
            "--output",
            report,
        ],
        [
            executable,
            "plan",
            "--sysfs",
            sysfs,
            *metadata,
            "--profiles",
            profiles,
            "--keyring",
            keyring,
            "--catalog-lock",
            catalog_lock,
            "--driver-abi",
            driver_abi,
            "--output",
            plan,
            "--require-target-profiles",
        ],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            return (_("Hardware preflight failed"), str(error))
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no diagnostic").strip()
            return (_("Hardware driver coverage is incomplete"), detail)
    libcalamares.globalstorage.insert("arachHardwareReport", report)
    libcalamares.globalstorage.insert("arachHardwarePlan", plan)
    return None
