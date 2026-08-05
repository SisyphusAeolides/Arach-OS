#!/usr/bin/env python3
import gettext
from pathlib import Path

import libcalamares

from adapter import (
    CATALOG_LOCK_PATH,
    KEYRING_PATH,
    MAPPING_PATH,
    PACMAN_PATH,
    PLAN_PATH,
    RECEIPT_PATH,
    RUNTIME_ROOT,
    SIGNATURE_PATH,
    SNAPSHOT_ROOT,
    PacmanAdapterError,
    execute_pacman,
    stage_and_authorize,
)


_ = gettext.translation(
    "calamares-python",
    localedir=libcalamares.utils.gettext_path(),
    languages=libcalamares.utils.gettext_languages(),
    fallback=True,
).gettext


def pretty_name():
    return _("Apply signed hardware package snapshot")


def pretty_status_message():
    return _("Authorizing hardware packages")


def run():
    configuration = libcalamares.job.configuration
    if set(configuration) != {"enabled"} or not isinstance(configuration["enabled"], bool):
        return (
            _("Invalid Pacman adapter configuration"),
            _("The adapter accepts only an explicit Boolean enabled setting"),
        )
    if not configuration["enabled"]:
        return None

    storage = libcalamares.globalstorage
    plan = storage.value("arachHardwarePlan")
    receipt = storage.value("arachHardwarePlanReceipt")
    target = storage.value("rootMountPoint")
    transaction_id = storage.value("arachTransactionId")
    if (
        plan != str(PLAN_PATH)
        or receipt != str(RECEIPT_PATH)
        or not isinstance(target, str)
        or not isinstance(transaction_id, str)
    ):
        return (
            _("Pacman adapter refused"),
            _("A verified Arach-HWD plan, target, or transaction is absent"),
        )
    try:
        snapshot, stage = stage_and_authorize(transaction_id)
        execute_pacman(Path(target), snapshot, stage)
    except PacmanAdapterError as error:
        return (_("Pacman adapter refused"), str(error))
    storage.insert("arachHardwarePacmanSnapshot", str(stage))
    return None
