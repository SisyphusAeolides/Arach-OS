#!/usr/bin/env python3
import gettext

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
    return _("Apply the Arach OS transaction")


def pretty_status_message():
    phase = libcalamares.job.configuration.get("phase", "unknown")
    return _("Arach OS transaction: {}").format(phase)


def run():
    configuration = libcalamares.job.configuration
    phase = configuration.get("phase")
    executable = configuration.get("executable")
    runtime_directory = configuration.get("runtimeDirectory")
    generation_source = configuration.get("generationSource")
    if (
        phase not in ("prepare", "commit")
        or not executable
        or not runtime_directory
        or not generation_source
    ):
        return ("Invalid Arach installer configuration", "Required transaction fields are absent")

    storage = libcalamares.globalstorage
    transaction_id = storage.value("arachTransactionId")
    if phase == "prepare":
        if transaction_id:
            return ("Arach transaction already exists", "Refusing to overwrite its journal")
        transaction_id = new_transaction_id()
        storage.insert("arachTransactionId", transaction_id)
    if not transaction_id:
        return ("Arach transaction is missing", "The prepare phase did not complete")

    transaction_paths = paths(runtime_directory, transaction_id)
    try:
        if phase == "prepare":
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
        return ("Arach OS transaction failed", str(error))
    return None
