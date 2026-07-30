# COSMIC live image and installer

The Arach OS installation medium starts `cosmic-comp` and `cosmic-session` as
its live desktop, then launches a branded Calamares process. There is no
alternate desktop in the release image.

Calamares owns interaction and delegates Arach-specific mutations to a
transaction engine. The engine produces a complete plan before changing disk
state and writes a recovery journal before the first destructive operation.

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
