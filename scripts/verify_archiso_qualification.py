#!/usr/bin/env python3
"""Verify structural ArchISO release inputs and retained qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")
FINGERPRINT_RE = re.compile(r"^[0-9A-F]{40,64}$")
PACKAGE_RE = re.compile(r"^[a-z0-9@._+:-]+$")
SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CHOICE_ID_RE = re.compile(r"^\s*-\s+id:\s*([a-z0-9-]+)\s*$", re.MULTILINE)
SCENARIOS = (
    "live-boot",
    "install",
    "reboot-installed",
    "update",
    "rollback",
)
KDE_PACKAGES = frozenset({"plasma-meta", "sddm", "polkit-kde-agent"})
GNOME_PACKAGES = frozenset({"gnome", "gdm"})
COSMIC_PACKAGES = frozenset(
    {"cosmic-session", "cosmic-comp", "cosmic-greeter", "xdg-desktop-portal-cosmic"}
)
BOOTLOADER_PACKAGES = frozenset({"grub", "efibootmgr", "systemd"})
REQUIRED_CHOICE_PACKAGES = (
    KDE_PACKAGES | GNOME_PACKAGES | COSMIC_PACKAGES | BOOTLOADER_PACKAGES
)
HWD_CONFIGURATION = {
    "executable": "/usr/bin/arach-hwd",
    "catalogSyncExecutable": "/usr/bin/arach-hwd-catalog-sync",
    "repositoryConfiguration": "/etc/arach/hwd/repository.toml",
    "remoteCatalogRoot": "/run/arach-installer/catalog",
    "sysfs": "/sys",
    "report": "/run/arach-installer/hardware.toml",
    "profiles": "/etc/arach/hwd/profiles",
    "keyring": "/etc/arach/hwd/keys.toml",
    "catalogLock": "/etc/arach/hwd/catalog.lock",
    "driverAbi": "/etc/arach/hwd/driver-abi",
    "binaryIndex": "/etc/arach/hwd/packages.toml",
    "binarySignature": "/etc/arach/hwd/packages.toml.sig",
    "plan": "/run/arach-installer/hardware.plan.toml",
    "planReceipt": "/run/arach-installer/hardware.plan.verified.json",
}
SISYPHUS_FINGERPRINT = "2A02745D8C2C03AE7F95BCEA8136EB9238213447"


class QualificationError(ValueError):
    """Raised when qualification inputs are not immutable and complete."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def verify_timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise QualificationError(f"{label} must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise QualificationError(f"{label} must be an RFC 3339 UTC timestamp") from error


def verify_digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise QualificationError(f"{label} must be a lowercase SHA-256 digest")


def verify_file(root: Path, relative: Any, digest: Any, label: str) -> None:
    if not safe_relative(relative):
        raise QualificationError(f"{label} path must be a safe relative path")
    verify_digest(digest, f"{label} digest")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"{label} is missing or not a regular file")
    if sha256(path) != digest:
        raise QualificationError(f"{label} digest does not match")


def verify_snapshot_url(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise QualificationError(f"{label} must use HTTPS")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise QualificationError(f"{label} must use a canonical HTTPS URL")
    host = parsed.hostname.casefold()
    if host == "aur.archlinux.org" or host.endswith(".aur.archlinux.org"):
        raise QualificationError(f"{label} must not use the AUR")


def require_profile_fragment(content: str, fragment: str, label: str) -> None:
    if fragment not in content:
        raise QualificationError(f"ArchISO profile is missing {label}")


def require_profile_configuration(
    content: str, expected: dict[str, str], label: str
) -> None:
    for key, value in expected.items():
        require_profile_fragment(content, f"{key}: {value}", f"{label} {key}")


def require_ordered_fragments(content: str, fragments: tuple[str, ...], label: str) -> None:
    position = -1
    for fragment in fragments:
        next_position = content.find(fragment, position + 1)
        if next_position == -1:
            raise QualificationError(f"ArchISO profile is missing {label}: {fragment}")
        position = next_position


def choice_ids(content: str, label: str) -> set[str]:
    choices = CHOICE_ID_RE.findall(content)
    if len(choices) != len(set(choices)):
        raise QualificationError(f"{label} contains duplicate choices")
    return set(choices)


def validate_profile_contract(profile_root: Path) -> None:
    """Validate the production profile's Calamares, HWD, and trust contract."""
    if profile_root.is_symlink() or not profile_root.is_dir():
        raise QualificationError("ArchISO profile root is missing or not a real directory")

    def read(relative: str) -> str:
        path = profile_root / relative
        if path.is_symlink() or not path.is_file():
            raise QualificationError(f"ArchISO profile file is missing or not regular: {relative}")
        return path.read_text(encoding="utf-8")

    settings = read("calamares/settings.conf")
    desktop = read("calamares/modules/desktop.conf")
    bootloader_choice = read("calamares/modules/bootloader-choice.conf")
    bootloader = read("calamares/modules/bootloader.conf")
    hardware = read("calamares/modules/arach-hardware.conf")
    pacman_adapter = read("calamares/modules/arach-pacman.conf")
    packages = read("packages.x86_64")
    pacman = read("pacman.conf")
    profile_definition = read("profiledef.sh")
    build = read("build.sh")
    customizer = read("airootfs/root/customize_airootfs.sh")
    keyring = read("airootfs/usr/share/pacman/keyrings/sisyphus-repo.asc")
    readme = read("README.md")

    require_ordered_fragments(
        settings,
        (
            "module: packagechooser\n    id: desktop\n    config: desktop.conf",
            "module: packagechooser\n    id: bootloader\n    config: bootloader-choice.conf",
            "module: arachhardware\n    id: hardware\n    config: arach-hardware.conf",
            "module: arachpacman\n    id: hardware-payloads\n    config: arach-pacman.conf",
            "module: bootloader\n    id: bootloader\n    config: bootloader.conf",
        ),
        "Calamares module wiring",
    )
    if settings.count("module: packagechooser") != 2:
        raise QualificationError("Calamares must expose exactly two package chooser modules")
    if set(re.findall(r"packagechooser@([a-z0-9-]+)", settings)) != {
        "desktop",
        "bootloader",
    }:
        raise QualificationError("Calamares must show exactly the desktop and bootloader choice pages")
    require_ordered_fragments(
        settings,
        (
            "\n      - arachhardware@hardware",
            "\n      - packages",
            "\n      - arachpacman@hardware-payloads",
            "\n      - bootloader@bootloader",
        ),
        "hardware installation sequence",
    )
    for fragment, label in (
        ("default: kde", "KDE as the default desktop"),
        ("id: kde", "the KDE choice"),
        ("packages: [ plasma-meta, sddm, polkit-kde-agent ]", "the KDE package set"),
        ("id: gnome", "the GNOME choice"),
        ("packages: [ gnome, gdm ]", "the GNOME package set"),
        ("id: cosmic", "the COSMIC choice"),
        (
            "packages: [ cosmic-session, cosmic-comp, cosmic-greeter, xdg-desktop-portal-cosmic ]",
            "the COSMIC package set",
        ),
    ):
        require_profile_fragment(desktop, fragment, label)
    if choice_ids(desktop, "desktop choices") != {"kde", "gnome", "cosmic"}:
        raise QualificationError("desktop choices must be exactly KDE, GNOME, and COSMIC")
    for fragment, label in (
        ("default: grub", "GRUB as the default bootloader"),
        ("id: grub", "the GRUB choice"),
        ("id: systemd-boot", "the systemd-boot choice"),
    ):
        require_profile_fragment(bootloader_choice, fragment, label)
    if choice_ids(bootloader_choice, "bootloader choices") != {"grub", "systemd-boot"}:
        raise QualificationError("bootloader choices must be exactly GRUB and systemd-boot")
    for fragment, label in (
        ('efiBootLoaderVar: "packagechooser_bootloader"', "the selected bootloader binding"),
        ('efiBootLoader: "grub"', "the GRUB default binding"),
    ):
        require_profile_fragment(bootloader, fragment, label)
    for package in BOOTLOADER_PACKAGES:
        require_profile_fragment(packages, f"{package}\n", f"the {package} package")
    require_profile_configuration(hardware, HWD_CONFIGURATION, "Arach-HWD configuration")
    for key in ("modulesAlias", "modulesFirmware", "modulesDep", "modulesBuiltin"):
        require_profile_fragment(hardware, f"{key}:", f"Arach-HWD {key} metadata")
    require_profile_fragment(
        hardware, "requireTargetProfiles: true", "Arach-HWD target-profile policy"
    )
    if pacman_adapter.strip() != "---\nenabled: true":
        raise QualificationError("signed Pacman adapter must be explicitly enabled")

    for fragment, label in (
        ("SigLevel = Required DatabaseRequired", "required repository signatures"),
        ("LocalFileSigLevel = Optional", "signed local snapshot policy"),
        ("[sisyphus]", "the signed Sisyphus repository"),
        ("Server = https://sisyphusaeolides.github.io/Sisyphus-Repo/$arch", "the Sisyphus source"),
        ("SigLevel = Required DatabaseRequired", "Sisyphus signature enforcement"),
    ):
        require_profile_fragment(pacman, fragment, label)
    if pacman.count("SigLevel = Required DatabaseRequired") != 2:
        raise QualificationError("Pacman must require signatures globally and for Sisyphus")
    for fragment, label in (
        ("key=/usr/share/pacman/keyrings/sisyphus-repo.asc", "Sisyphus keyring path"),
        (f"fingerprint={SISYPHUS_FINGERPRINT}", "pinned Sisyphus fingerprint"),
        ('pacman-key --add "$key"', "keyring import"),
        ('pacman-key --lsign-key "$fingerprint"', "local key trust"),
    ):
        require_profile_fragment(customizer, fragment, label)
    if (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----" not in keyring
        or "-----END PGP PUBLIC KEY BLOCK-----" not in keyring
    ):
        raise QualificationError("Sisyphus keyring must contain an armored public key")

    for fragment, label in (
        ('readonly catalog_root="${ARACH_HWD_CATALOG_ROOT:', "signed HWD catalog input"),
        ('readonly snapshot_root="${ARACH_HWD_PACMAN_SNAPSHOT_ROOT:', "signed Pacman snapshot input"),
        ('"${source_modules}/arachhardware"', "Arach-HWD module installation"),
        ('"${source_modules}/arachpacman"', "Pacman adapter installation"),
        ('"${snapshot_root}/pacman-snapshot.toml"', "signed Pacman mapping installation"),
        ('"${snapshot_root}/pacman-snapshot.toml.sig"', "Pacman mapping signature installation"),
        ('"${snapshot_root}/pacman-snapshot.gpg"', "Pacman snapshot keyring installation"),
        ('"${snapshot_root}/pacman.conf"', "signed Pacman configuration installation"),
    ):
        require_profile_fragment(build, fragment, label)
    for required_input in (
        "keys.toml",
        "catalog.lock",
        "packages.toml",
        "packages.toml.sig",
        "driver-abi",
        "pacman-snapshot.toml",
        "pacman-snapshot.toml.sig",
        "pacman-snapshot.gpg",
    ):
        require_profile_fragment(build, required_input, f"required signed input {required_input}")
    for required_directory in (
        '"${catalog_root}/profiles"',
        '"${catalog_root}/driver-sources"',
        '"${snapshot_root}/packages"',
    ):
        require_profile_fragment(build, required_directory, f"required directory {required_directory}")

    if "aur.archlinux.org" in pacman.casefold():
        raise QualificationError("ArchISO profile must not configure the AUR")
    for content, label in (
        (settings, "Calamares settings"),
        (desktop, "desktop choices"),
        (bootloader_choice, "bootloader choices"),
        (bootloader, "bootloader configuration"),
        (hardware, "Arach-HWD configuration"),
        (pacman_adapter, "Pacman adapter configuration"),
        (packages, "package list"),
        (profile_definition, "ArchISO boot configuration"),
        (build, "ArchISO build script"),
    ):
        if "limine" in content.casefold():
            raise QualificationError(f"Limine must not be exposed by {label}")
    require_profile_fragment(readme, "Limine remains experimental", "Limine experimental status")


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualificationError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise QualificationError(f"{label} must be a JSON object")
    return value


def verify_signed_file(
    root: Path, entry: dict[str, Any], label: str, *, file_field: str = "path"
) -> None:
    expected = {file_field, "sha256", "signature", "signature_sha256", "signer_fingerprint"}
    if set(entry) != expected:
        raise QualificationError(f"{label} has unexpected or missing fields")
    verify_file(root, entry[file_field], entry["sha256"], label)
    verify_file(root, entry["signature"], entry["signature_sha256"], f"{label} signature")
    if not isinstance(entry["signer_fingerprint"], str) or not FINGERPRINT_RE.fullmatch(
        entry["signer_fingerprint"]
    ):
        raise QualificationError(f"{label} signer_fingerprint must be a full OpenPGP fingerprint")


def load_evidence_json(root: Path, entry: dict[str, Any], label: str) -> dict[str, Any]:
    verify_file(root, entry["path"], entry["sha256"], label)
    return load_json(root / entry["path"], label)


def verify_sbom(
    root: Path, entry: dict[str, Any], packages: list[dict[str, Any]], package_set_sha256: str
) -> None:
    if entry["package_set_sha256"] != package_set_sha256:
        raise QualificationError("sbom does not bind the package list")
    document = load_evidence_json(root, entry, "sbom")
    expected_versions = {package["name"]: package["version"] for package in packages}
    if entry["format"] == "spdx-json":
        if not isinstance(document.get("spdxVersion"), str) or not document["spdxVersion"].startswith(
            "SPDX-"
        ):
            raise QualificationError("sbom must be a valid SPDX JSON document")
        reported = document.get("packages")
        name_field, version_field = "name", "versionInfo"
    else:
        if document.get("bomFormat") != "CycloneDX" or not isinstance(
            document.get("specVersion"), str
        ):
            raise QualificationError("sbom must be a valid CycloneDX JSON document")
        reported = document.get("components")
        name_field, version_field = "name", "version"
    if not isinstance(reported, list):
        raise QualificationError("sbom must enumerate every immutable package")
    observed: dict[str, str] = {}
    for item in reported:
        if not isinstance(item, dict):
            raise QualificationError("sbom package entries must be objects")
        name, version = item.get(name_field), item.get(version_field)
        if not isinstance(name, str) or not isinstance(version, str) or name in observed:
            raise QualificationError("sbom package entries must have unique names and versions")
        observed[name] = version
    if observed != expected_versions:
        raise QualificationError("sbom package names and versions must match the immutable package lock")


def verify_provenance(
    root: Path, entry: dict[str, Any], package_set_sha256: str
) -> None:
    if entry["package_set_sha256"] != package_set_sha256:
        raise QualificationError("provenance does not bind the package list")
    document = load_evidence_json(root, entry, "provenance")
    if (
        document.get("_type") != "https://in-toto.io/Statement/v1"
        or not isinstance(document.get("predicateType"), str)
        or not document["predicateType"]
        or not isinstance(document.get("predicate"), dict)
        or not isinstance(document.get("subject"), list)
    ):
        raise QualificationError("provenance must be an in-toto statement with subjects")
    for subject in document["subject"]:
        if (
            isinstance(subject, dict)
            and subject.get("name") == "arachos-package-set"
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha256") == package_set_sha256
        ):
            return
    raise QualificationError("provenance must bind the immutable package set")


def validate_package_lock(root: Path, document: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "format",
        "distribution",
        "archiso_profile_revision",
        "snapshot",
        "packages",
        "package_set_sha256",
        "sbom",
        "provenance",
    }
    if set(document) != expected:
        raise QualificationError("package lock has unexpected or missing fields")
    if document["format"] != 1 or document["distribution"] != "ArachOS":
        raise QualificationError("package lock identity is invalid")
    revision = document["archiso_profile_revision"]
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise QualificationError("archiso_profile_revision must be a full Git object ID")

    snapshot = document["snapshot"]
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "id",
        "repository",
        "generated_at",
        "database",
        "keyring",
        "verification",
    }:
        raise QualificationError("snapshot has unexpected or missing fields")
    if not isinstance(snapshot["id"], str) or not SNAPSHOT_ID_RE.fullmatch(snapshot["id"]):
        raise QualificationError("snapshot.id must be a canonical immutable identifier")
    verify_snapshot_url(snapshot["repository"], "snapshot.repository")
    if snapshot["id"] not in urlparse(snapshot["repository"]).path.split("/"):
        raise QualificationError("snapshot.repository must identify snapshot.id")
    verify_timestamp(snapshot["generated_at"], "snapshot.generated_at")
    if not isinstance(snapshot["database"], dict):
        raise QualificationError("snapshot.database must be an object")
    verify_signed_file(root, snapshot["database"], "snapshot database")
    if not isinstance(snapshot["keyring"], dict) or set(snapshot["keyring"]) != {"path", "sha256"}:
        raise QualificationError("snapshot keyring has unexpected or missing fields")
    verify_file(root, snapshot["keyring"]["path"], snapshot["keyring"]["sha256"], "snapshot keyring")
    verification = snapshot["verification"]
    if not isinstance(verification, dict) or set(verification) != {"path", "sha256", "tool"}:
        raise QualificationError("snapshot verification has unexpected or missing fields")
    if verification["tool"] not in {"gpgv", "pacman-key"}:
        raise QualificationError("snapshot verification tool must be gpgv or pacman-key")
    verify_file(root, verification["path"], verification["sha256"], "snapshot verification transcript")

    packages = document["packages"]
    if not isinstance(packages, list) or not packages:
        raise QualificationError("packages must be a non-empty array")
    names: set[str] = set()
    for index, package in enumerate(packages):
        label = f"packages[{index}]"
        if not isinstance(package, dict) or set(package) != {
            "name",
            "version",
            "architecture",
            "repository",
            "archive",
        }:
            raise QualificationError(f"{label} has unexpected or missing fields")
        if not isinstance(package["name"], str) or not PACKAGE_RE.fullmatch(package["name"]):
            raise QualificationError(f"{label}.name is invalid")
        if package["name"] in names:
            raise QualificationError(f"{label}.name is duplicated")
        names.add(package["name"])
        if not isinstance(package["version"], str) or not package["version"]:
            raise QualificationError(f"{label}.version must be non-empty")
        if package["architecture"] not in {"x86_64", "aarch64"}:
            raise QualificationError(f"{label}.architecture is unsupported")
        if package["repository"] != snapshot["repository"]:
            raise QualificationError(f"{label}.repository must match the immutable snapshot repository")
        if not isinstance(package["archive"], dict):
            raise QualificationError(f"{label}.archive must be an object")
        verify_signed_file(root, package["archive"], f"{label} archive")

    package_set_sha256 = canonical_sha256(packages)
    if document["package_set_sha256"] != package_set_sha256:
        raise QualificationError("package_set_sha256 does not bind the package list")
    missing_choices = sorted(REQUIRED_CHOICE_PACKAGES - names)
    if missing_choices:
        raise QualificationError(
            "immutable snapshot does not supply required desktop or bootloader packages: "
            + ", ".join(missing_choices)
        )
    for label in ("sbom", "provenance"):
        entry = document[label]
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "format", "package_set_sha256"}:
            raise QualificationError(f"{label} has unexpected or missing fields")
    if document["sbom"]["format"] not in {"spdx-json", "cyclonedx-json"}:
        raise QualificationError("sbom must use SPDX or CycloneDX JSON")
    if document["provenance"]["format"] != "in-toto-statement":
        raise QualificationError("provenance must use an in-toto statement")
    verify_sbom(root, document["sbom"], packages, package_set_sha256)
    verify_provenance(root, document["provenance"], package_set_sha256)
    return {
        "snapshot_sha256": snapshot["database"]["sha256"],
        "package_set_sha256": package_set_sha256,
        "packages": len(packages),
    }


def validate_qemu_report(
    root: Path, document: dict[str, Any], package_lock_sha256: str, snapshot_sha256: str
) -> int:
    expected = {
        "format",
        "captured_at",
        "package_lock_sha256",
        "image",
        "image_sha256",
        "qemu",
        "firmware",
        "initial_snapshot_sha256",
        "update_snapshot_sha256",
        "scenarios",
    }
    if set(document) != expected:
        raise QualificationError("QEMU report has unexpected or missing fields")
    if document["format"] != 1:
        raise QualificationError("QEMU report format is invalid")
    verify_timestamp(document["captured_at"], "QEMU report captured_at")
    if document["package_lock_sha256"] != package_lock_sha256:
        raise QualificationError("QEMU report does not bind the package lock")
    verify_file(root, document["image"], document["image_sha256"], "QEMU image")
    firmware = document["firmware"]
    if not isinstance(firmware, dict) or set(firmware) != {"path", "sha256"}:
        raise QualificationError("QEMU firmware evidence has unexpected or missing fields")
    verify_file(root, firmware["path"], firmware["sha256"], "QEMU firmware")
    if document["initial_snapshot_sha256"] != snapshot_sha256:
        raise QualificationError("QEMU report initial snapshot differs from the package lock")
    verify_digest(document["update_snapshot_sha256"], "QEMU report update snapshot")
    if document["update_snapshot_sha256"] == snapshot_sha256:
        raise QualificationError("QEMU report update snapshot must differ from the initial snapshot")
    qemu = document["qemu"]
    if not isinstance(qemu, dict) or set(qemu) != {"binary", "version", "machine", "firmware_sha256"}:
        raise QualificationError("QEMU environment has unexpected or missing fields")
    if qemu["binary"] != "qemu-system-x86_64" or not isinstance(qemu["version"], str) or not qemu["version"]:
        raise QualificationError("QEMU x86_64 binary and version must be recorded")
    if qemu["machine"] != "q35":
        raise QualificationError("QEMU machine must be q35")
    verify_digest(qemu["firmware_sha256"], "QEMU firmware")
    if qemu["firmware_sha256"] != firmware["sha256"]:
        raise QualificationError("QEMU firmware digest differs from retained firmware evidence")

    scenarios = document["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) != len(SCENARIOS):
        raise QualificationError("QEMU report must contain all five scenarios")
    expected_transitions = (
        (snapshot_sha256, snapshot_sha256, False),
        (snapshot_sha256, snapshot_sha256, True),
        (snapshot_sha256, snapshot_sha256, True),
        (snapshot_sha256, document["update_snapshot_sha256"], True),
        (document["update_snapshot_sha256"], snapshot_sha256, True),
    )
    for index, (scenario, expected_id, transition) in enumerate(
        zip(scenarios, SCENARIOS, expected_transitions, strict=True)
    ):
        label = f"scenarios[{index}]"
        if not isinstance(scenario, dict) or set(scenario) != {
            "id",
            "status",
            "log",
            "log_sha256",
            "snapshot_before_sha256",
            "snapshot_after_sha256",
            "post_reboot",
        }:
            raise QualificationError(f"{label} has unexpected or missing fields")
        if scenario["id"] != expected_id:
            raise QualificationError(f"{label}.id differs from canonical qualification order")
        if scenario["status"] != "passed":
            raise QualificationError(f"{label} did not pass")
        verify_file(root, scenario["log"], scenario["log_sha256"], f"{label} log")
        before, after, reboot = transition
        if (
            scenario["snapshot_before_sha256"] != before
            or scenario["snapshot_after_sha256"] != after
            or scenario["post_reboot"] is not reboot
        ):
            raise QualificationError(f"{label} has an invalid snapshot or reboot transition")
    return len(scenarios)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-lock", required=True, type=Path)
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--qemu-report", type=Path)
    parser.add_argument("--qemu-artifacts-root", type=Path)
    parser.add_argument(
        "--profile-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "archiso",
        help="ArchISO profile whose selectable desktop and bootloader contract is validated",
    )
    arguments = parser.parse_args()
    if bool(arguments.qemu_report) != bool(arguments.qemu_artifacts_root):
        parser.error("--qemu-report and --qemu-artifacts-root must be supplied together")
    try:
        lock = arguments.package_lock.resolve(strict=True)
        lock_bytes_sha256 = sha256(lock)
        validate_profile_contract(arguments.profile_root)
        inputs = validate_package_lock(arguments.artifacts_root.resolve(strict=True), load_json(lock, "package lock"))
        message = f"ArchISO package lock: {inputs['packages']} packages, immutable snapshot verified"
        if arguments.qemu_report:
            report = load_json(arguments.qemu_report.resolve(strict=True), "QEMU report")
            count = validate_qemu_report(
                arguments.qemu_artifacts_root.resolve(strict=True),
                report,
                lock_bytes_sha256,
                inputs["snapshot_sha256"],
            )
            message += (
                f"; retained QEMU evidence: {count}/5 scenarios structurally verified"
                " (not a claim of real QEMU or hardware qualification)"
            )
        print(message)
    except (OSError, QualificationError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
