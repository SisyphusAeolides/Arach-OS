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
- **Arach-HWD** — hardware detection and driver provisioning (planned)

The exact revisions used by an image are recorded in
[`components.lock.toml`](components.lock.toml). Independent repositories remain
the development authorities until their histories are deliberately consolidated
into this monorepo.

## Desktop and installer

The live image boots directly into COSMIC and launches a branded Calamares
installer. The installer transaction covers storage, encryption, users,
passwords, locale, timezone, keyboard, packages, Granite, the COSMIC greeter,
and post-install boot verification. See [`docs/INSTALLER.md`](docs/INSTALLER.md).

The canonical logo is [`branding/arach-logo.png`](branding/arach-logo.png).
Despite the extension of the originally supplied file, its actual format is a
706×706 RGBA PNG; the original bytes are retained under `branding/source/`.

## Current status

The composition contract and component pins are established. A bootable live
ISO, complete package repository, hardware-profile database, and full COSMIC
behavior gate remain active implementation work.
