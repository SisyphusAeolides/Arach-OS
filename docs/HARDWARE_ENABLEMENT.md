# Automatic hardware enablement

Arach-HWD follows a scan, resolve, plan, apply, verify, and rollback pipeline.
It runs in the live image, during installation, at first boot, and for hotplug.

The scanner records PCI, USB, ACPI, DMI, device-tree, firmware, and native
capability facts. A profile is eligible only when every required match clause
passes. The resolver selects the highest-priority non-conflicting signed
profile and asks Corinth to stage the exact driver and firmware transaction.

C drivers use the stable Arach Driver ABI through a small C shim and execute in
isolated driver cells. Prebuilt Linux kernel modules are not treated as native
Arach drivers. Linux C source can be adapted, rebuilt, measured, and packaged
when its hardware semantics can be expressed through the Arach ABI.

Every profile records supported device IDs, ABI range, package identity,
firmware requirements, conflicts, initramfs requirements, health checks, and
rollback instructions. Unknown required fields or an unverified post-activate
device state abort the transaction.
