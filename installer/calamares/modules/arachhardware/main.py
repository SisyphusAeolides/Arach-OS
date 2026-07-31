#!/usr/bin/env python3
import gettext
from pathlib import Path
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
    report = configuration.get("report")
    if (
        executable != "/system/arach-hwd"
        or sysfs != "/sys"
        or report != "/run/arach-installer/hardware.toml"
    ):
        return (_("Invalid hardware preflight configuration"), _("Required paths are absent"))
    try:
        report_parent = Path(report).parent
        report_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        return (_("Hardware preflight failed"), str(error))
    try:
        result = subprocess.run(
            [executable, "preflight", "--sysfs", sysfs, "--output", report],
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
    return None
