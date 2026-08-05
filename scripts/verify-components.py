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
STALE_PRODUCT = re.compile(r"\bArach(?:[ \t\r\n]+|-)OS\b")


def load_lock(path: pathlib.Path) -> list[dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"format", "distribution", "composition", "release_role", "component"}:
        raise ValueError("lock contains missing or unknown top-level fields")
    if (
        data["format"] != 1
        or data["distribution"] != "ArachOS"
        or data["composition"] != "native-stack"
        or data["release_role"] != "experimental"
    ):
        raise ValueError("lock is not the experimental native-stack composition")
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


def validate_rust_pins(
    components: list[dict[str, str]], manifest_path: pathlib.Path
) -> None:
    """Ensure host-side Rust integration uses the locked component objects.

    The live-image lock is the release authority, but arach-compose and
    Corinth also import Arach-HWD at build time. Allowing either manifest to
    drift creates two Rust crate identities with the same package name and
    silently breaks the installer boundary.
    """
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ValueError("Cargo.toml has no dependency table")
    locked = {component["name"]: component["revision"] for component in components}
    for package_name, component_name in (("corinth", "corinth"), ("arach-hwd", "arach-hwd")):
        dependency = dependencies.get(package_name)
        if not isinstance(dependency, dict):
            raise ValueError(f"Cargo.toml dependency {package_name} must be a Git table")
        if dependency.get("git") != (
            f"https://github.com/SisyphusAeolides/{'Corinth' if package_name == 'corinth' else 'Arach-HWD'}.git"
        ):
            raise ValueError(f"Cargo.toml dependency {package_name} repository differs")
        if dependency.get("rev") != locked[component_name]:
            raise ValueError(
                f"Cargo.toml dependency {package_name} revision differs from components.lock.toml"
            )


def show_remote_file(directory: str, path: str) -> str:
    result = subprocess.run(
        ["git", "-C", directory, "show", f"FETCH_HEAD:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"locked component is missing {path}: {result.stderr.strip()}")
    return result.stdout


def validate_nested_authority(
    component: dict[str, str], directory: str, locked: dict[str, str]
) -> None:
    if component["name"] == "corinth":
        manifest = tomllib.loads(show_remote_file(directory, "Cargo.toml"))
        dependencies = manifest.get("dependencies")
        dependency = (
            dependencies.get("arach-hwd")
            if isinstance(dependencies, dict)
            else None
        )
        if (
            not isinstance(dependency, dict)
            or dependency.get("git")
            != "https://github.com/SisyphusAeolides/Arach-HWD.git"
            or dependency.get("rev") != locked["arach-hwd"]
        ):
            raise ValueError("locked Corinth imports a different Arach-HWD revision")
    if component["name"] != "arach-packages":
        return
    for recipe_path, repository, component_name in (
        (
            "recipes/base/corinth/package.toml",
            "https://github.com/SisyphusAeolides/Corinth.git",
            "corinth",
        ),
        (
            "recipes/base/arach-hwd/package.toml",
            "https://github.com/SisyphusAeolides/Arach-HWD.git",
            "arach-hwd",
        ),
    ):
        recipe = tomllib.loads(show_remote_file(directory, recipe_path))
        sources = recipe.get("source")
        if (
            not isinstance(sources, list)
            or len(sources) != 1
            or not isinstance(sources[0], dict)
            or sources[0].get("kind") != "git"
            or sources[0].get("url") != repository
            or sources[0].get("revision") != locked[component_name]
        ):
            raise ValueError(
                f"locked Arach-Packages {component_name} recipe differs from the component graph"
            )
    kernel_recipe = tomllib.loads(
        show_remote_file(directory, "recipes/base/arach-kernel/package.toml")
    )
    kernel_sources = kernel_recipe.get("source")
    expected_kernel_sources = [
        {
            "kind": "git",
            "url": "https://github.com/SisyphusAeolides/Arach-Kernel.git",
            "revision": locked["arach-kernel"],
            "submodules": False,
        },
        {
            "kind": "git",
            "url": "https://github.com/SisyphusAeolides/Push.git",
            "revision": locked["push"],
            "submodules": False,
        },
    ]
    if kernel_sources != expected_kernel_sources:
        raise ValueError(
            "locked Arach-Packages kernel recipe differs from the component graph"
        )


def verify_remote(component: dict[str, str], locked: dict[str, str]) -> str:
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
        validate_nested_authority(component, directory, locked)
    return component["name"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, default=pathlib.Path("Cargo.toml"))
    parser.add_argument("--remote", action="store_true")
    arguments = parser.parse_args()
    components = load_lock(arguments.lock)
    validate(components)
    validate_rust_pins(components, arguments.manifest)
    if arguments.remote:
        locked = {
            component["name"]: component["revision"] for component in components
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            futures = [
                workers.submit(verify_remote, component, locked)
                for component in components
            ]
            for future in futures:
                future.result()
    print(f"verified {len(components)} exact ArachOS component pins")


if __name__ == "__main__":
    main()
