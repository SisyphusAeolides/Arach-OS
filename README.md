<p align="center">
  <img src="branding/arach-logo.png" width="360" alt="Arach OS logo">
</p>

# Arach OS

Arach OS is an experimental operating-system distribution built around Arach
Kernel and the COSMIC Epoch desktop. This repository is the composition and
release authority: it pins independently versioned components, defines the
live image and installer, selects signed package snapshots, and runs the
cross-component foundation, image, and desktop gates.

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
the development authorities; this lock is the release authority for a composed
Arach OS image.

## Current release authority

The current closed component graph pins:

- Arach Kernel `8559a34ac79d23c0074686d3522568207444967f`;
- Corinth `711be83330ed12291d98f68bc1de4dc2805ef9c4`;
- Arach-Packages `b7fc47a4e7e1293c26d3fc50abf3ca98a589c1f4`;
- Arach-HWD `8a02fa4a41d5e21b447a92414db23b4b706f3731`;
- exact Granite, Push, Slope, libinput-rs, elan-guardian, tuned-rs, and ccze-rs
  revisions recorded beside them in the lock.

The pinned kernel contains the measured Akashic VFS-backed Linux file bridge,
generation-bound `set_tid_address` exit clearing, private futex
compare/block/wake, generation-safe x86-64 FS-base TLS, and independently
measured shared-address-space clone, robust owner-death wake, descriptor
sharing, clear-child-tid wake, bounded x86-64 self-signal delivery and
exact-frame return, measured multi-member `exit_group`, and transactional
static and `PT_INTERP` `execve` with atomic executable/interpreter snapshots,
independent measurements, one composite W^X image, a System V auxiliary
vector, measured linker-to-main transfer, same-PID image exchange,
close-on-exec and signal transitions, and deferred old-root reclamation. The
pinned kernel also provides bounded generation-owned private file mappings,
zero-filled file tails, exact whole-mapping W^X protection transitions, and
rollback-safe page-table updates. Its measured C linker now closes a bounded
four-object dependency diamond within an eight-object engine. It performs
breadth-first discovery, coalesces both middle dependencies onto one core
snapshot, rejects cycles, computes provider-first relocation order, validates
SysV hash chains and dynamic symbols, applies five real relative relocations,
one static-TLS relocation, and four real external PLT relocations through
deterministic global scope. It builds a bounded initial TLS arena, establishes
an x86-64 FS-base thread pointer, seals all objects to final W^X segment
permissions, runs four dependency-first initializers, and executes through both
branches while consuming their shared relocated and FS-relative state. A dense
generation-bound descriptor/open-object table
now unifies standard streams, files, eventfd, timerfd, epoll, and anonymous
pipes; it supplies alias-safe `dup` and bounded `fcntl`, descriptor-local
close-on-exec, poll/epoll readiness, and exact last-close watch removal. The
same table carries bounded Unix stream socketpairs and named listeners with
full-duplex and vector transfer, peer identity, half-close, and measured
QEMU/OVMF readiness evidence. Bounded `SCM_RIGHTS` now transfers exact open
descriptions across process generations, while generation-bound memfds provide
shared physical mappings that survive descriptor close. The pinned package
repository contains kernel recipe release 31, Corinth recipe
release 34, Elan Guardian 0.2.6, and
installer recipe release 24, including the exact Calamares and transaction
outputs required by the image. The pinned Corinth service retains multiple
native package versions under signed monotonic sequences, resolves signed
cross-provider runtime dependency and virtual-capability graphs
deterministically, and commits each dependency-first install or update through
one recoverable journal. The standard package lifecycle also preserves exact
version pins and refuses conflicts, ambiguity, cycles, reverse-dependency
removal, and sequence downgrades.
Signed source catalogs route Arch/AUR, Fedora specs, Debian control files,
Alpine APKBUILDs, Gentoo ebuilds, CRUX Pkgfiles, fixed-output Nix exports, and
Cargo closures through one measured ingress. Dynamic packaging scripts remain
outside this static admission boundary.
The final foundation matrix verifies every remote revision, strict Rust checks,
Fortran, Idris 2, Agda, live-root composition, SquashFS construction, and UEFI
ISO layout before publication.

This is a release-graph and image-construction qualification. It is not yet a
claim that the image reaches a complete COSMIC session under QEMU or on
physical hardware.

## Desktop and installer

The live-image contract installs the locked `cosmic-desktop` bundle, including
the complete pinned COSMIC Epoch component tree, the pinned `greetd` display
manager and `cosmic-greeter` session configuration, `cosmic-term`, and the
signed Firefox runtime artifact. It is designed to boot directly into COSMIC
and launch a branded Calamares installer; SDDM is not part of this path.

Calamares 3.4.2 is pinned to an exact upstream Codeberg object. Its native
modules own storage, encryption, users, passwords, locale, timezone, and
keyboard configuration. The Arach transaction boundary owns the immutable
Corinth package plan, Granite activation, COSMIC verification, and rollback
journal. See [`docs/INSTALLER.md`](docs/INSTALLER.md).

The installer recipe publishes the journaled `arach-install` binary, canonical
branding, Calamares settings, hardware-preflight modules, transaction modules,
and the native partition, user, and unpack configuration consumed by the live
image. Package and OS validation both check those declared outputs exactly.

The canonical logo is [`branding/arach-logo.png`](branding/arach-logo.png).
The retained source bytes are stored under `branding/source/`.

### Desktop boundary

COSMIC is the only desktop shipped by Arach OS: `seatd` owns the login seat,
`greetd` launches `cosmic-greeter`, `pipewire` and `wireplumber` provide the
audio session, and the greeter starts `cosmic-comp`. The session, portal,
terminal, and all other pinned COSMIC outputs are copied from the complete
`cosmic-desktop` tree.

Crest is **not** a desktop environment, desktop package, compositor, session,
or greeter. The lowercase `crest` file retained inside the measured Granite
boot bundle is a compatibility-named C0 bootstrap/probe payload required by the
current handoff. It never enters the live provider set, and the composition
validator rejects any Crest-named desktop provider.

## Hardware boundary

The medium ships `/system/arach-hwd` and the signed
`arach-hardware-catalog` at `/etc/arach/hwd`. Calamares preflight enumerates
network/Wi-Fi, audio, graphics, storage, input, Bluetooth, firmware, and other
hardware evidence, resolves detached-signature profiles, and writes the exact
Corinth plan before partitioning.

The catalog lock carries hashed `modules.alias`, `modules.dep`,
`modules.builtin`, `modules.firmware`, and `modules.builtin.modinfo` target
metadata under `/etc/arach/hwd/driver-sources`. HWD uses those files before
comparing live, staged-target, or offline module and firmware trees. A physical
device with no bound driver or compatible signed target profile stops the
install; no package is guessed from an interface or class name.

The signed catalog is therefore a required release artifact, not an optional
fallback. Passing the catalog and image gates does not claim universal hardware
coverage: installability still depends on an exact signed profile, package
intent, payload, and compatible Driver ABI.

## Current status

The composition contract, exact component pins, Calamares configuration,
private state handoff, journal-bound transaction state machine, signed Corinth
artifact materializer, live-root assembler, SquashFS image, and UEFI ISO builder
are established and exercised in CI.

The production transaction can validate and publish a canonical Corinth
generation with a target-persistent recovery checkpoint, atomically activate a
manifest-bound Granite/Arach/Push/C0 boot bundle, verify installed artifacts,
and restore both boot files and package authority after process or machine
interruption. The image gate now constructs the required live root and UEFI ISO
instead of treating those artifacts as future work.

The remaining qualification boundary is explicit:

- the UEFI ISO has not yet completed a full boot-to-COSMIC login/session gate;
- the kernel's current Akashic file storage is bounded and ephemeral rather
  than persistent and block-backed;
- process-shared and priority-inheritance futexes, general clone/fork modes,
  asynchronous cross-process signals, and complete leader-exit semantics
  remain incomplete;
- native graphics, audio, networking, suspend/resume, and broad physical
  hardware operation still require end-to-end runtime evidence.

Rust validates the executable image and installer contracts. Fortran schedules
only trust-admitted build stages and rejects an installer missing a transaction
guard. The total Idris model and safe Agda model require exact component pins,
encode the readiness chain, and make mutation without a durable journal and
secret-bearing handoff values unconstructable.

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
```

Execute an ISO assembled with measured Arach boot artifacts under OVMF and
require the ring-3 native, Linux-personality, four-object dependency-graph,
relative and static-TLS relocation, eager external-symbol binding,
dependency-first initialization, and final process-lifecycle evidence with:

```sh
scripts/run-live-iso-qemu.sh /absolute/path/to/arach-os.iso
```

The image-construction test accepts `ARACH_TEST_BOOT_ARTIFACT_ROOT` to replace
its four header fixtures with a directory containing `granite.efi`, `arach`,
`push`, and `crest`. `ARACH_TEST_ISO_OUTPUT` preserves that assembled test ISO
for the execution gate. The foundation workflow builds those four artifacts
from the exact locked revisions, boots the resulting ISO, and retains its
serial transcript and image sidecar as qualification evidence. Neither option
weakens the default structural tests.

Build the installer input bundle with:

```sh
scripts/assemble-boot-bundle.sh ARTIFACT_DIR /run/arach-live/boot-bundle
```

`ARTIFACT_DIR` must contain the measured Granite PE/COFF image, ELF `arach` and
`push` images, and the measured C0 probe supplied in the compatibility slot
named `crest`. The latter is a boot probe, not a desktop image. The assembler
writes the bounded, digest-bound manifest consumed by `arach-install`.

The live-root boundary is explicit in [`live/image.toml`](live/image.toml), and
the package-to-runtime mapping is locked in
[`live/system.toml`](live/system.toml).

`scripts/materialize-live-system.sh` consumes versioned Corinth artifact
directories, rejects symlinks and path escapes, installs measured Push,
Corinth, D-Bus, greetd, the complete COSMIC tree, Firefox, Calamares, and the
installer, then writes `/run/arach-live/system.json`. It requires the display
manager, greeter configuration, terminal, and browser before publishing the
root.

`scripts/assemble-live-root.sh` consumes that POSIX root, the manifest-bound
Granite/Arach/Push/C0 bundle, and a signed Corinth generation. It refuses to
publish unless both manifests and the complete runtime path set are present.
Finally, `scripts/build-live-iso.sh` creates the UEFI ISO with xorriso, places
Granite at `/EFI/BOOT/BOOTX64.EFI`, and preserves its measured `/BOOT` inputs.
The command exits with status 69 when xorriso is unavailable instead of
publishing an unqualified image.
