#!/usr/bin/env python3
import gettext
import pathlib

import libcalamares

from protocol import (
    TransactionFailure,
    atomic_json,
    collect_state,
    execute,
    new_transaction_id,
    paths,
)


_ = gettext.translation(
    "calamares-python",
    localedir=libcalamares.utils.gettext_path(),
    languages=libcalamares.utils.gettext_languages(),
    fallback=True,
).gettext


def pretty_name():
    return _("Apply the ArachOS transaction")


def pretty_status_message():
    phase = libcalamares.job.configuration.get("phase", "unknown")
    return _("ArachOS transaction: {}").format(phase)


def run():
    configuration = libcalamares.job.configuration
    storage = libcalamares.globalstorage
    phase = configuration.get("phase")
    executable = configuration.get("executable")
    runtime_directory = configuration.get("runtimeDirectory")
    generation_source = configuration.get("generationSource")
    boot_bundle_source = configuration.get("bootBundleSource")
    hardware_profiles = configuration.get("hardwareProfiles")
    hardware_keyring = configuration.get("hardwareKeyring")
    hardware_catalog_lock = configuration.get("hardwareCatalogLock")
    hardware_binary_index = configuration.get("hardwareBinaryIndex")
    hardware_binary_signature = configuration.get("hardwareBinarySignature")

    if phase == "commit":
        hardware_profiles = storage.value("arachHardwareProfiles") or hardware_profiles
        hardware_keyring = storage.value("arachHardwareKeyring") or hardware_keyring
        hardware_catalog_lock = (
            storage.value("arachHardwareCatalogLock") or hardware_catalog_lock
        )
        hardware_binary_index = (
            storage.value("arachHardwareBinaryIndex") or hardware_binary_index
        )
        hardware_binary_signature = (
            storage.value("arachHardwareBinarySignature")
            or hardware_binary_signature
        )
        catalog_root = storage.value("arachHardwareCatalogRoot")
        if catalog_root:
            expected = pathlib.Path(catalog_root)
            if catalog_root not in (
                "/etc/arach/hwd",
                "/run/arach-installer/catalog",
            ) or (
                pathlib.Path(hardware_profiles) != expected / "profiles"
                or pathlib.Path(hardware_keyring) != expected / "keys.toml"
                or pathlib.Path(hardware_catalog_lock) != expected / "catalog.lock"
                or pathlib.Path(hardware_binary_index) != expected / "packages.toml"
                or pathlib.Path(hardware_binary_signature)
                != expected / "packages.toml.sig"
            ):
                return (
                    "Invalid Arach installer configuration",
                    "Hardware transaction paths differ from the verified catalog",
                )

    if (
        phase not in ("prepare", "commit")
        or not executable
        or not runtime_directory
        or not generation_source
        or not boot_bundle_source
        or (
            phase == "commit"
            and (
                not hardware_profiles
                or not hardware_keyring
                or not hardware_catalog_lock
                or not hardware_binary_index
                or not hardware_binary_signature
            )
        )
    ):
        return (
            "Invalid Arach installer configuration",
            "Required transaction fields are absent",
        )

    transaction_id = storage.value("arachTransactionId")
    if phase == "prepare":
        if transaction_id:
            return (
                "Arach transaction already exists",
                "Refusing to overwrite its journal",
            )
        transaction_id = new_transaction_id()
        storage.insert("arachTransactionId", transaction_id)
    if not transaction_id:
        return (
            "Arach transaction is missing",
            "The prepare phase did not complete",
        )

    transaction_paths = paths(runtime_directory, transaction_id)
    try:
        if phase == "prepare":
            hardware_plan = storage.value("arachHardwarePlan")
            if hardware_plan != "/run/arach-installer/hardware.plan.toml":
                raise TransactionFailure("hardware preflight plan is missing")
            hardware_plan_path = pathlib.Path(hardware_plan)
            if not hardware_plan_path.is_file() or hardware_plan_path.is_symlink():
                raise TransactionFailure(
                    "hardware preflight plan is not a regular file"
                )
            state = collect_state(storage.value, transaction_id)
            atomic_json(transaction_paths["state"], state)
            execute(
                [
                    executable,
                    "prepare",
                    "--state",
                    str(transaction_paths["state"]),
                    "--plan",
                    str(transaction_paths["plan"]),
                    "--journal",
                    str(transaction_paths["journal"]),
                    "--generation",
                    str(generation_source),
                    "--boot-bundle",
                    str(boot_bundle_source),
                    "--hardware-plan",
                    hardware_plan,
                ]
            )
        else:
            target = storage.value("rootMountPoint")
            if not target:
                raise TransactionFailure("Calamares did not provide rootMountPoint")
            try:
                execute(
                    [
                        executable,
                        "apply",
                        "--plan",
                        str(transaction_paths["plan"]),
                        "--journal",
                        str(transaction_paths["journal"]),
                        "--target",
                        str(target),
                        "--boot-bundle",
                        str(boot_bundle_source),
                        "--hardware-profiles",
                        str(hardware_profiles),
                        "--hardware-keyring",
                        str(hardware_keyring),
                        "--hardware-catalog-lock",
                        str(hardware_catalog_lock),
                        "--hardware-binary-index",
                        str(hardware_binary_index),
                        "--hardware-binary-signature",
                        str(hardware_binary_signature),
                        "--hardware-work",
                        str(transaction_paths["base"] / "hardware-work"),
                        "--hardware-artifacts",
                        str(transaction_paths["base"] / "hardware-artifacts"),
                    ]
                )
                execute(
                    [
                        executable,
                        "verify",
                        "--plan",
                        str(transaction_paths["plan"]),
                        "--journal",
                        str(transaction_paths["journal"]),
                        "--target",
                        str(target),
                    ]
                )
            except TransactionFailure:
                execute(
                    [
                        executable,
                        "rollback",
                        "--plan",
                        str(transaction_paths["plan"]),
                        "--journal",
                        str(transaction_paths["journal"]),
                        "--target",
                        str(target),
                    ]
                )
                raise
    except TransactionFailure as error:
        return ("ArachOS transaction failed", str(error))
    return None
