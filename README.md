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

The live-image contract boots directly into COSMIC and launches a branded
Calamares installer. Calamares 3.4.2 is pinned to an exact upstream Codeberg
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
The production transaction currently fails closed before changing the target
because durable Corinth installation and Granite activation are not implemented
yet. A bootable live ISO, complete package repository, hardware-profile
database, and full COSMIC behavior gate remain active implementation work.

Rust validates the executable image and installer contracts. Fortran schedules
only trust-admitted build stages and rejects an installer missing any transaction
guard. The total Idris model and safe Agda model require exact component pins,
encode the readiness chain, and make mutation without a durable journal and
secret-bearing handoff values unconstructable.

## Validation

    cargo fmt --all -- --check
    cargo clippy --locked --all-targets -- -D warnings
    cargo test --locked
    cargo run --locked -- verify --root .
    scripts/verify-foundation.sh
    scripts/check-fortran.sh
    scripts/check-formal-models.sh
