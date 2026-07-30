# COSMIC live image and installer

The Arach OS installation medium starts `cosmic-comp` and `cosmic-session` as
its live desktop, then launches a branded Calamares process. There is no
alternate desktop in the release image.

Calamares owns interaction and delegates Arach-specific mutations to a
transaction engine. The reviewed installer baseline is Calamares 3.4.2 from
`https://codeberg.org/Calamares/calamares.git`, peeled to Git object
`36d30c492e5c7b5d6d32fed5c5d9790522e1eea3`. The engine produces a complete
plan before changing disk state and writes a recovery journal before the first
destructive operation.

The `arachtransaction@prepare` job runs before Calamares' partition job. It
passes only an allowlisted state document to `arach-install`; user, root, and
LUKS secrets remain inside Calamares. The `arachtransaction@commit` job runs
after mount and unpack, then requests apply and verify and invokes rollback on
failure. Every subprocess uses an argument array with `shell=False`.

Before its first Corinth mutation, the backend fsyncs an immutable plan,
generation image, and recovery journal into the mounted target. It publishes
the canonical Corinth generation, mirrors every subsequent journal transition
to that checkpoint, and can recover an interrupted transaction with
`arach-install recover --target <root>`. The Calamares failure path performs the
same rollback immediately. The backend then deliberately reports unavailable
at the Granite gate: package artifact deployment, measured boot activation, and
their remaining inverse operations are not implemented, so this is not yet a
bootable installation path.

## Required pages

1. language, locale, timezone, and keyboard;
2. network and optional repository refresh;
3. destination disk and explicit destructive-action confirmation;
4. automatic, alongside, replace, and manual partitioning;
5. optional full-disk encryption and recovery-key confirmation;
6. hostname, user, administrator policy, and password creation;
7. package profile and optional hardware/firmware review;
8. immutable summary, install, verification, and reboot.

## Filesystem matrix

- EFI system partition: FAT32;
- root: Btrfs, ext4, XFS, or F2FS;
- home: Btrfs, ext4, XFS, or F2FS;
- swap: partition or supported swapfile configuration;
- Bcachefs and ZFS: hidden until their kernel, repair, boot, encryption, and
  rollback gates are independently proven.

## Completion gate

An installation is successful only after Corinth verifies the installed
package generation, Granite is installed and measured, the account database is
readable, COSMIC greeter configuration is present, the target root can be
mounted read-write, and an isolated boot probe reaches the configured session.
