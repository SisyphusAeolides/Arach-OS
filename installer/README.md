# ArachOS installer integration

The ArachOS installer targets the exact Calamares revision recorded in
[`contract.toml`](contract.toml). The COSMIC live session installs the canonical
ArachOS branding asset into Calamares and requires the complete display,
session, portal, audio, and installer runtime before the image can be
published.

## Runtime boundary

The live session uses:

- `seatd` for seat permissions;
- `greetd` and the pinned COSMIC greeter configuration;
- `dbus-broker` for desktop IPC;
- PipeWire and WirePlumber for media policy;
- `cosmic-comp`, `cosmic-greeter`, `cosmic-session`, and the COSMIC portal;
- `arach-install` for the journaled target transaction.

SDDM is not part of the ArachOS runtime path.

## Hardware preflight

The signed hardware catalog contains profiles, detached signatures, package
metadata, and target-kernel evidence. Its lock covers:

- `modules.alias`;
- `modules.dep`;
- `modules.builtin`;
- `modules.firmware`;
- `modules.builtin.modinfo`.

Calamares passes those exact files to Arach-HWD before partitioning. A live
Linux driver binding is not treated as proof that the target Arach kernel has a
qualified driver. Unresolved physical devices remain a hard failure unless the
operation is explicitly inventory-only.

## Transaction lifecycle

The external `arachtransaction` module has two instances:

1. `prepare` runs before storage mutation and requires `arach-install` to create
   the immutable plan and recovery journal.
2. `commit` runs after the target root is mounted and unpacked; it applies and
   verifies the plan and invokes rollback on failure.

The handoff excludes user passwords, the root password, and the LUKS
passphrase. Commands are executed as argument arrays and never through a shell.

`arach-install prepare` validates the private state document, Corinth
generation, and live boot-bundle manifest. Apply persists a recovery bundle on
the target before publishing package authority and atomically activates the
measured Granite, Arach, Push, and bootstrap artifacts. Verify re-hashes those
artifacts. `arach-install recover --target <root>` restores the same state after
a restart.

## Boot bundle

The complete native COSMIC bundle contains:

```text
manifest.json
granite.efi
arach
push
crest
seatd
dbus-broker
pipewire
wireplumber
cosmic-comp
cosmic-greeter
cosmic-session
xdg-desktop-portal-cosmic
```

The lowercase `crest` file is the measured C0 bootstrap/probe compatibility
slot. It is not a desktop environment, package, compositor, session, or
greeter.

The installer accepts the native COSMIC bundle only when every required ELF
file and manifest digest is present. Partial service sets are rejected. The
four-artifact C0 bundle remains a separate compatibility qualification path.

## Certification

Installer qualification is tracked by
[`../production/installer-recovery.json`](../production/installer-recovery.json).
Clean install, reinstall, dual boot, encryption, TPM recovery, Secure Boot,
interrupted partitioning, disk full, corrupted cache, power loss, failed-kernel
rollback, rescue media, and major-version upgrade remain independently
certified scenarios. A scenario cannot pass without hash-bound recovery, boot,
and COSMIC evidence.
