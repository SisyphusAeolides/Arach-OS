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

The live-image contract installs the locked `cosmic-desktop` bundle, including
the complete pinned COSMIC Epoch component tree, plus the pinned `greetd`
display manager, its `cosmic-greeter` session configuration, the `cosmic-term`
terminal, and the signed Firefox runtime artifact. It boots directly into
COSMIC and launches a branded Calamares installer; SDDM is not part of this
path. Calamares 3.4.2 is pinned to an exact upstream Codeberg
object. Its native modules own storage, encryption, users, passwords, locale,
timezone, and keyboard configuration. The Arach transaction boundary owns the
immutable Corinth package plan, Granite activation, COSMIC verification, and
rollback journal. See [`docs/INSTALLER.md`](docs/INSTALLER.md).

The canonical logo is [`branding/arach-logo.png`](branding/arach-logo.png).
Despite the extension of the originally supplied file, its actual format is a
706×706 RGBA PNG; the original bytes are retained under `branding/source/`.

### Desktop boundary

COSMIC is the only desktop shipped by Arach OS: `greetd` launches
`cosmic-greeter`, which starts `cosmic-comp`; the session, portal, terminal,
and all other pinned COSMIC component outputs are copied from the complete
`cosmic-desktop` tree. Crest is **not** a desktop environment,
desktop package, compositor, session, or greeter in this distribution. The
lowercase `crest` file retained inside the measured Granite boot bundle is a
compatibility-named C0 bootstrap/probe payload required by the current Granite
handoff; it never enters the live system provider set. The composition validator
and materializer reject any Crest-named desktop provider.

## Current status

The composition contract, component pins, Calamares configuration, private
state handoff, journal-bound transaction state machine, and signed
Corinth-artifact-to-live-root materializer are established.
The production transaction can now validate and publish a canonical Corinth
generation with a target-persistent recovery checkpoint, atomically activate a
manifest-bound Granite/Arach/Push/C0 boot bundle, verify the installed
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

`ARTIFACT_DIR` must contain the measured Granite PE/COFF image, ELF `arach` and
`push` images, and the measured C0 probe artifact supplied in the compatibility
slot named `crest`. The latter is a boot probe, not a desktop image. The
assembler writes the bounded, digest-bound manifest consumed by
`arach-install`.

The live-root boundary is explicit in [`live/image.toml`](live/image.toml), and
the package-to-runtime mapping is locked in [`live/system.toml`](live/system.toml).
`scripts/materialize-live-system.sh` consumes the versioned Corinth artifact
directories, rejects symlinks and path escapes, installs the measured Push,
Corinth, D-Bus, greetd, the complete COSMIC tree (including its greetd config
and `cosmic-term`), Firefox, Calamares, and installer paths, and writes
`/run/arach-live/system.json`. The materializer requires the display manager,
greeter configuration, terminal, and browser before it publishes the live
root, so the Calamares session never starts without them.
`scripts/assemble-live-root.sh`
then consumes
that POSIX root, the manifest-bound Granite/Arach/Push/C0 bundle, and a
signed Corinth generation. It refuses to publish a root unless both system and
image manifests are present and the complete runtime path set is present.
Finally, `scripts/build-live-iso.sh` creates the UEFI-bootable ISO with
xorriso, placing Granite at `/EFI/BOOT/BOOTX64.EFI` and preserving its
measured `/BOOT` inputs; the command exits with status 69 when xorriso is not
installed rather than publishing an unqualified image.
