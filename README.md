<p align="center">
  <img src="branding/arach-logo.png" width="360" alt="ArachOS logo">
</p>

# ArachOS

ArachOS is an experimental operating-system distribution built around Arach
Kernel and the COSMIC Epoch desktop. This repository is the composition and
release authority. It pins independently versioned components, defines the
live image and Calamares installer, selects signed Corinth package generations,
and enforces production-readiness evidence.

Repository: `https://github.com/SisyphusAeolides/ArachOS`

## Component graph

The exact release graph is recorded in
[`components.lock.toml`](components.lock.toml). The current lock contains:

- Arach Kernel — kernel and Linux/POSIX compatibility boundary
- Granite — measured UEFI bootloader
- Push — PID 1 and service supervisor
- Slope — userspace ABI and runtime library
- Corinth — transactional package manager and recipe import authority
- Arach-Packages — native recipes, generated recipe corpus, SBOMs, and source policy
- Arach-HWD — signed hardware discovery, provisioning, and qualification
- libinput-rs, elan-guardian, tuned-rs, and ccze-rs — separately versioned system components

Symbolic branches are not release inputs. Component revisions, package sources,
workflow checkouts, and qualification evidence are bound to full Git object IDs
and SHA-256 digests.

## Desktop and installer

COSMIC is the only ArachOS desktop. The live image requires the complete
session path: seatd, D-Bus, PipeWire, WirePlumber, greetd, cosmic-greeter,
cosmic-comp, cosmic-session, xdg-desktop-portal-cosmic, and the pinned COSMIC
application tree.

The Calamares integration uses the journaled `arach-install` transaction
engine. It prepares an immutable plan before mutation, persists recovery state,
activates the measured Granite/Arach/Push boot bundle, verifies installed
artifacts, and rolls back package and boot authority after failure or restart.
See [`docs/INSTALLER.md`](docs/INSTALLER.md) and
[`installer/README.md`](installer/README.md).

## Package compatibility program

ArachOS treats universal compatibility as a routing problem. A workload may use
one of five tested routes:

1. native ArachOS recipe;
2. source rebuild;
3. compatibility runtime;
4. container;
5. managed virtual machine.

The production package target is **39,191 canonical recipes**. Corinth provides
static importers for Arch/AUR PKGBUILDs, Fedora specs, Debian control files,
Alpine APKBUILDs, Gentoo ebuilds, CRUX Pkgfiles, fixed-output Nix exports, and
Cargo crates. Dynamic package logic is assigned to a capability-bounded,
deterministic compatibility worker instead of being executed in the native
recipe path.

The first large upstream conversion source is the CachyOS PKGBUILD repository.
Arach-Packages locks its repository revision, inventories every `PKGBUILD`,
assigns deterministic shards, and converts static metadata through Corinth.
Packages that cannot pass the static parser retain an explicit worker request
and blocker rather than being silently accepted.

## Production readiness

The release authority is fail-closed. The machine-readable ledgers under
[`production/`](production/) cover:

- COSMIC lifecycle;
- Linux/POSIX compatibility;
- hardware and driver coverage;
- Corinth indexing and package semantics;
- compatibility workers and application routes;
- package-repository completeness;
- installer and recovery certification;
- desktop services;
- security qualification;
- hardware-lab and release operations.

A gate cannot become qualified while blockers remain or without retained,
revision-bound, SHA-256-verified evidence. Current status is intentionally
reported by the ledgers and validators rather than by prose claims in this
README.

## Validation

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
cargo run --locked --bin arach-compose -- verify --root .
scripts/verify-foundation.sh
scripts/check-fortran.sh
scripts/check-formal-models.sh
scripts/test-live-root.sh
python3 scripts/verify_production_readiness.py --root . --report
python3 scripts/verify_control_matrices.py --root .
python3 scripts/verify_installer_recovery.py --root .
python3 scripts/verify_threat_model.py --root .
python3 scripts/verify_release_channels.py --root .
```

A measured ISO can be executed under QEMU/OVMF with:

```sh
scripts/run-live-iso-qemu.sh /absolute/path/to/arachos.iso
```

Passing structural, build, or QEMU gates does not by itself claim complete
physical-hardware support. Certified, Compatible, and Experimental hardware
levels require their own retained lifecycle and soak evidence.

## License

MIT

## Current ArachOS integration status

This project is maintained as part of the ArachOS production graph. Its role is
the release composition authority, installer, production gates, and evidence ledger..

CI and release evidence are evaluated on immutable revisions. Hardware support
is reported by bounded route and support level; this README does not claim
universal native support. Gate 3 requires signed hardware identity, target
kernel provenance, package authority, health checks, rollback behavior, and
representative physical-hardware evidence before production qualification.
