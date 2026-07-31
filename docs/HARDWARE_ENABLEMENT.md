# Automatic hardware enablement

Arach-HWD follows a scan, resolve, plan, apply, verify, and rollback pipeline.
It runs in the live image, during installation, at first boot, and for hotplug.

The scanner records PCI, USB, I2C, ACPI, DMI, Linux class devices, firmware,
and native capability facts. Inventory schema 2 groups network, wireless,
audio, graphics, storage, input, Bluetooth, and firmware while preserving
stable modalias queries. A profile is eligible only when every required match
clause passes. The resolver selects the highest-priority non-conflicting
signed profile and asks Corinth to stage the exact driver and firmware
transaction.

The Calamares medium carries `/system/arach-hwd`. Its first execution job
runs `arach-hwd preflight --sysfs /sys` and writes
`/run/arach-installer/hardware.toml`. An unbound physical device stops the
installation before partitioning, leaving its modalias and bus identity in
the report for a signed Arach Hardware profile to resolve. Virtual network
interfaces and child ALSA/DRM/block/input class nodes are not mistaken for
missing drivers.

C drivers use the stable Arach Driver ABI through a small C shim and execute in
isolated driver cells. Prebuilt Linux kernel modules are not treated as native
Arach drivers. Linux C source can be adapted, rebuilt, measured, and packaged
when its hardware semantics can be expressed through the Arach ABI.

Every profile records supported device IDs, ABI range, package identity,
firmware requirements, conflicts, initramfs requirements, health checks, and
rollback instructions. Unknown required fields or an unverified post-activate
device state abort the transaction.
