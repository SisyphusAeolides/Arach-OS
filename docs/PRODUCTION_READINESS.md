# Production readiness tracker

This tracker captures the remaining production-readiness gates and turns the raw
list into concrete acceptance checkpoints. It is the implementation target for the
`Remaining production-readiness gates` document used by the project.

## 1. Full COSMIC lifecycle

- Target: prove installer → reboot → greeter → login → usable desktop → suspend/resume
  → logout → shutdown end-to-end on QEMU and hardware.
- Current status: `in_progress`
- Detailed path and marker plan: [`COSMIC_LIFECYCLE_GATE.md`](COSMIC_LIFECYCLE_GATE.md)
- Next evidence to collect:
  - QEMU serial markers for greeter session launch
  - evidence of reachable desktop shell session
  - suspend/resume, logout, and shutdown traces
  - parity evidence on at least one representative physical machine

## 2. Complete Linux/POSIX compatibility

- Target: process groups, signals, threading, file/mount semantics, permissions,
  IPC, Unix sockets, shared memory, networking, DNS/DHCP/netlink, PTYs, `/proc`,
  `/sys`, `/dev`, uevents, mmap pressure handling, credentials, capabilities,
  and broad ioctl compatibility.
- Current status: `in_progress`

## 3. Production hardware and driver coverage

- Target: ACPI, PCIe, IOMMU, storage, USB, DRM/KMS, evdev, ALSA/SOF, Wi‑Fi,
  Ethernet, Bluetooth, webcams, battery, thermal, docks, displays, suspend,
  hibernation, hot-plug; plus bounded Linux compatibility for non-native drivers.
- Current status: `in_progress`

## 4. Automatic Corinth repository service

- Target: continuously running upstream indexers across Arch/AUR, Fedora, Debian,
  Alpine, Gentoo, CRUX, Nix, Cargo, GitHub; immutable revisions; canonical
  recipes; dependency closure; catalog signing and publishing; compromise/remove
  handling.
- Current status: `in_progress`

## 5. Broader package semantics

- Target: replacements, optional/feature dependencies, split packages,
  devel/debug outputs, multilib, config merges, ownership/permissions, safe
  symlinks/hardlinks, xattrs, ACLs, file capabilities, users/groups,
  service declarations, desktop registration, triggers.
- Current status: `in_progress`

## 6. Dynamic compatibility workers

- Target: sandboxed workers for complex PKGBUILD/spec/rules/ebuild/setup workflows
  with declared capabilities, deterministic FS/network boundaries, and measured,
  reproducible outputs.
- Current status: `in_progress`

## 7. Linux application compatibility tiers

- Target: complete glibc/musl, FHS, ELF interpreter, syscall/ioctl compatibility,
  managed Flatpak/OCI/AppImage routes, and lightweight VM fallback for legacy
  proprietary packages.
- Current status: `in_progress`

## 8. Complete the package repository

- Target: broad first-party package set with build/install/update/remove/rollback
  and runtime tests, including toolchains, libc/OpenSSL/networking, office,
  browsers, media, drivers, firmware, and diagnostics.
- Current status: `in_progress`

## 9. Installer and recovery certification

- Target: clean install/reinstall/dual-boot/encrypted-TPM/secure-boot, failure and
  power-loss drills, rescue operations, kernel rollback, major upgrade recovery.
- Current status: `in_progress`

## 10. Desktop services

- Target: networking, Wi‑Fi auth, DNS, D-Bus, portals, audio policy,
  Bluetooth audio, credentials/authz, printing, storage/media/cameras/notifications,
  updates, diagnostics, locale/fonts, input methods, accessibility, power.
- Current status: `in_progress`

## 11. Security qualification

- Target: threat models, fuzzing, hardening (ASLR/W^X/stack protections/SMEP/SMAP/IOMMU),
  privilege separation, app sandboxing, key management + rotation/revocation, SBOMs,
  attestations, reproducible builds, vuln intake, and patch SLAs.
- Current status: `in_progress`

## 12. Hardware lab and release operations

- Target: repeatable matrix testing by model/vendor, published support tiers
  (Certified/Compatible/Experimental), channel operations, mirrors, rollback drills,
  advisories, and soak testing.
- Current status: `in_progress`

## 13. Universal route statement

- The target is that every workload has a clearly tested route:
  native, rebuilt, compatibility runtime, container, or managed VM.
- Current status: `in_progress`
