#!/usr/bin/env python3
import argparse
import concurrent.futures
import pathlib
import re
import subprocess
import tempfile
import tomllib


EXPECTED = {
    "arach-kernel": ("Arach-Kernel", "kernel"),
    "slope": ("Slope", "userspace-abi"),
    "push": ("Push", "pid1"),
    "granite": ("Granite", "bootloader"),
    "corinth": ("Corinth", "package-manager"),
    "arach-packages": ("Arach-Packages", "package-recipes"),
    "arach-hwd": ("Arach-HWD", "hardware-provisioning"),
    "libinput-rs": ("libinput-rs", "input-stack"),
    "elan-guardian": ("elan-guardian", "input-recovery"),
    "tuned-rs": ("tuned-rs", "system-tuning"),
    "ccze-rs": ("ccze-rs", "log-presentation"),
}
REVISION = re.compile(r"[0-9a-f]{40}")


def load_lock(path: pathlib.Path) -> list[dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"format", "distribution", "component"}:
        raise ValueError("lock contains missing or unknown top-level fields")
    if data["format"] != 1 or data["distribution"] != "Arach OS":
        raise ValueError("lock format or distribution identity is invalid")
    components = data["component"]
    if not isinstance(components, list):
        raise ValueError("component must be an array of tables")
    return components


def validate(components: list[dict[str, str]]) -> None:
    actual = {}
    repositories = set()
    for component in components:
        if set(component) != {"name", "repository", "revision", "role"}:
            raise ValueError("component contains missing or unknown fields")
        name = component["name"]
        if name in actual:
            raise ValueError(f"duplicate component {name}")
        if not REVISION.fullmatch(component["revision"]):
            raise ValueError(f"{name} revision is not a lowercase full object ID")
        if component["repository"] in repositories:
            raise ValueError(f"duplicate repository {component['repository']}")
        repositories.add(component["repository"])
        actual[name] = component
    if set(actual) != set(EXPECTED):
        missing = sorted(set(EXPECTED) - set(actual))
        extra = sorted(set(actual) - set(EXPECTED))
        raise ValueError(f"component set differs: missing={missing}, extra={extra}")
    for name, (repository_name, role) in EXPECTED.items():
        component = actual[name]
        expected_repository = (
            f"https://github.com/SisyphusAeolides/{repository_name}.git"
        )
        if component["repository"] != expected_repository:
            raise ValueError(f"{name} repository differs from its authority")
        if component["role"] != role:
            raise ValueError(f"{name} role differs from the composition contract")


def verify_remote(component: dict[str, str]) -> str:
    with tempfile.TemporaryDirectory(prefix="arach-component-") as directory:
        subprocess.run(
            ["git", "init", "--bare", "--quiet", directory],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        result = subprocess.run(
            [
                "git",
                "-C",
                directory,
                "fetch",
                "--quiet",
                "--no-tags",
                "--depth=1",
                component["repository"],
                component["revision"],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(
                f"{component['name']} revision is unavailable: {result.stderr.strip()}"
            )
        fetched = subprocess.run(
            ["git", "-C", directory, "rev-parse", "FETCH_HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if fetched != component["revision"]:
            raise ValueError(f"{component['name']} fetched object differs from its pin")
    return component["name"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=pathlib.Path, required=True)
    parser.add_argument("--remote", action="store_true")
    arguments = parser.parse_args()
    components = load_lock(arguments.lock)
    validate(components)
    if arguments.remote:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(verify_remote, components))
    print(f"verified {len(components)} exact Arach OS component pins")


if __name__ == "__main__":
    main()
