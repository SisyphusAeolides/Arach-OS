<p align="center">
  <img src="branding/arach-logo.png" width="360" alt="Arach OS logo">
</p>

# Arach OS

Arach OS is an experimental operating-system distribution built around Arach
Kernel and the COSMIC Epoch desktop. This repository is the composition and
release authority: it pins independently versioned system components, defines
the live image and installer, selects signed package snapshots, and runs the
cross-component boot and desktop gates.

## Component repositories

- **Arach Kernel** — monolithic kernel and native driver boundary
- **Granite** — measured UEFI bootloader
- **Push** — PID 1 and service supervisor
- **Slope** — userspace ABI and runtime library
- **Corinth** — source and binary package manager
- **Arach-Packages** — signed recipes and immutable source locks
- **Arach-HWD** — signed hardware detection and Corinth provisioning plans

The exact revisions used by an image are recorded in
[`components.lock.toml`](components.lock.toml). Independent repositories remain
the development authorities until their histories are deliberately consolidated
into this monorepo.

## Desktop and installer

The live-image contract installs the locked `cosmic-desktop` bundle, boots
directly into COSMIC, and launches a branded Calamares installer. Calamares 3.4.2 is pinned to an exact upstream Codeberg
object. Its native modules own storage, encryption, users, passwords, locale,
timezone, and keyboard configuration. The Arach transaction boundary owns the
immutable Corinth package plan, Granite activation, COSMIC verification, and
rollback journal. See [`docs/INSTALLER.md`](docs/INSTALLER.md).

The canonical logo is [`branding/arach-logo.png`](branding/arach-logo.png).
Despite the extension of the originally supplied file, its actual format is a
706×706 RGBA PNG; the original bytes are retained under `branding/source/`.

## Current status

The composition contract, component pins, Calamares configuration, private
state handoff, and journal-bound transaction state machine are established.
The production transaction can now validate and publish a canonical Corinth
generation with a target-persistent recovery checkpoint, atomically activate a
manifest-bound Granite/Arach/Push/Crest boot bundle, verify the installed
artifacts, and restore both boot files and package authority after process or
machine interruption. A bootable live ISO, complete package repository,
hardware-profile database, and full COSMIC behavior gate remain active work;
the installer still fails closed when the live boot bundle is absent or does
not match its plan.

Rust validates the executable image and installer contracts. Fortran schedules
only trust-admitted build stages and rejects an installer missing any transaction
guard. The total Idris model and safe Agda model require exact component pins,
encode the readiness chain, and make mutation without a durable journal and
secret-bearing handoff values unconstructable.

## Validation

    cargo fmt --all -- --check
    cargo clippy --locked --all-targets -- -D warnings
    cargo test --locked
    cargo run --locked --bin arach-compose -- verify --root .
    scripts/verify-foundation.sh
    scripts/check-fortran.sh
    scripts/check-formal-models.sh

Build the installer input bundle with:

    scripts/assemble-boot-bundle.sh ARTIFACT_DIR /run/arach-live/boot-bundle

`ARTIFACT_DIR` must contain the measured Granite PE/COFF image and ELF
`arach`, `push`, and `crest` artifacts. The assembler writes the bounded,
digest-bound manifest consumed by `arach-install`.

The live-root boundary is explicit in [`live/image.toml`](live/image.toml).
`scripts/assemble-live-root.sh` consumes a package-built POSIX root, the
manifest-bound Granite/Arach/Push/Crest bundle, and a signed Corinth
generation. It refuses to publish a root unless the complete Push, COSMIC,
Calamares, and installer executable set is present, then writes a deterministic
image manifest. An ISO writer still consumes this assembled root as a separate,
tool-qualified release step.
