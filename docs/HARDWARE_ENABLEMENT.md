# Automatic hardware enablement

Arach-HWD follows a scan, resolve, plan, apply, verify, and rollback pipeline.
It runs in the live image, during installation, at first boot, and for hotplug.

The scanner records PCI, USB, I2C, ACPI, DMI, Linux class devices, firmware,
and native capability facts. Inventory schema 5 groups network, wireless,
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
The installer configuration accepts repeatable absolute `modulesAlias`,
`modulesFirmware`, `modulesDep`, and `modulesBuiltin` paths plus real-directory
`firmwareRoots`; image builders may
pin both live and target kernel metadata tables. Empty lists now discover every
regular table in the live kernel, `/usr/lib/modules`,
`/run/arach/target-modules`, and staged `/mnt` module roots, so driver and
firmware candidates do not depend on which kernel booted the medium. `modules.dep`
binds candidates to exact payload paths and `modules.builtin` records
drivers compiled into the target kernel. Every configured table is required to
be a regular file and every configured firmware root a non-symlink directory
before Calamares invokes HWD. Empty `firmwareRoots` uses the live and staged
firmware roots discovered by HWD.
The report is written to `/run/arach-installer/hardware.toml` and the exact
Corinth plan to `/run/arach-installer/hardware.plan.toml`. An unbound physical
device, a physical function with no target profile, invalid signature, or
incompatible Driver ABI stops the installation before partitioning. A driver
bound by the temporary live Linux kernel is not treated as proof that the
target Arach kernel has that driver. Virtual network interfaces and child
ALSA/DRM/block/input class nodes are not mistaken for missing drivers.

Every inventory and preflight report also carries a `driver_sources` manifest.
It records SHA-256 digests for the exact kernel metadata tables consulted,
including the kernel release scope for conventional
`/.../modules/<release>/modules.*` paths, and the firmware discovery roots
visible to the live installer. The signed
Arach-HWD profile/index and Arach-Packages recipe authorities are the only
sources allowed to authorize installation; upstream Linux kernel and
linux-firmware trees remain broad, advisory lookup evidence. This preserves
reproducibility while allowing a Calamares medium to compare its live kernel
with the target Arach kernel and discover Wi-Fi, audio, graphics, storage,
input, Bluetooth, and firmware candidates before partitioning. The catalog
lock also binds the exact Arach-Packages repository revision used for source
fallback; the installer consumes that value instead of embedding a moving
package commit in its executable.

For unresolved devices, the report retains source-scoped candidate fields
(candidate_*_sources) in addition to module and firmware names. These fields
identify the exact live or staged modules.alias, modules.firmware, modules.dep,
or modules.builtin table that produced each candidate, so a target-kernel
result cannot be mistaken for evidence from the temporary live kernel.

The catalog also carries `packages.toml` and its detached signature. This is
the scoped `package-index` for prebuilt Arach hardware payloads (kernel driver
trees and firmware). At commit, Corinth verifies the index with the catalog
keyring and installs an exact binary plan when every intent is covered; if a
signed intent has no binary record, Corinth fetches the pinned Arach-Packages
revision from the catalog lock and builds the locked `@install-tree` recipe
instead. Both paths write
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
