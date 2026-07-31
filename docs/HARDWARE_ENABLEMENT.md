# Automatic hardware enablement

Arach-HWD follows a scan, resolve, plan, apply, verify, and rollback pipeline.
It runs in the live image, during installation, at first boot, and for hotplug.

The scanner records PCI, USB, I2C, ACPI, DMI, Linux class devices, firmware,
and native capability facts. Inventory schema 3 groups network, wireless,
audio, graphics, storage, input, Bluetooth, and firmware while preserving
stable modalias queries. A profile is eligible only when every required match
clause passes. The resolver selects the highest-priority non-conflicting
signed profile and asks Corinth to stage the exact driver and firmware
transaction.

The Calamares medium carries `/system/arach-hwd` plus the signed
`arach-hardware-catalog` tree at `/etc/arach/hwd`. Its first execution job
runs `arach-hwd preflight --sysfs /sys` and then resolves the same inventory
through the detached-signature profiles and keyring with
`arach-hwd plan --require-target-profiles`.
The installer configuration accepts repeatable absolute `modulesAlias` and
`modulesFirmware` paths; image builders may pin both live and target kernel
metadata tables, while empty lists retain deterministic running-kernel
autodiscovery. Every configured table is required to be a regular file before
Calamares invokes HWD.
The report is written to `/run/arach-installer/hardware.toml` and the exact
Corinth plan to `/run/arach-installer/hardware.plan.toml`. An unbound physical
device, a physical function with no target profile, invalid signature, or
incompatible Driver ABI stops the installation before partitioning. A driver
bound by the temporary live Linux kernel is not treated as proof that the
target Arach kernel has that driver. Virtual network interfaces and child
ALSA/DRM/block/input class nodes are not mistaken for missing drivers.

The catalog also carries `packages.toml` and its detached signature. This is
the scoped `package-index` for prebuilt Arach hardware payloads (kernel driver
trees and firmware). At commit, Corinth verifies the index with the catalog
keyring and installs an exact binary plan when every intent is covered; if a
signed intent has no binary record, Corinth fetches the pinned Arach-Packages
revision and builds the locked `@install-tree` recipe instead. Both paths write
the same owned-file receipt set under the transaction and rollback removes only
those measured files. A missing index, profile, signature, recipe, or digest is
a hard failure, never an unverified fallback.

The catalog is a release input, not a guessed package list: each profile must
bind the exact bus/modalias identity to signed Arach hardware artifacts,
firmware, health checks, and rollback data. A live image without this catalog
is rejected by the image contract instead of silently installing a system with
unknown hardware coverage.

C drivers use the stable Arach Driver ABI through a small C shim and execute in
isolated driver cells. Prebuilt Linux kernel modules are not treated as native
Arach drivers. Linux C source can be adapted, rebuilt, measured, and packaged
when its hardware semantics can be expressed through the Arach ABI.

Every profile records supported device IDs, ABI range, package identity,
firmware requirements, conflicts, initramfs requirements, health checks, and
rollback instructions. Unknown required fields or an unverified post-activate
device state abort the transaction.
