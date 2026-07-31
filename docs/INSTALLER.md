# COSMIC live image and installer

The Arach OS installation medium installs the complete pinned `cosmic-desktop`
tree, the pinned `greetd` display manager, the upstream
`/etc/greetd/cosmic-greeter.toml` session definition, `cosmic-term`, the signed
Firefox runtime artifact, and the `arach-os-installer` recipe outputs from the
locked Arach-Packages workspace. `greetd` launches `cosmic-greeter`, which runs
inside `cosmic-comp`; the live session then starts `cosmic-session`. SDDM is
not used. The medium launches a branded Calamares process;

Crest is deliberately absent from this desktop and package graph. The
compatibility-named `crest` file in the boot bundle is only the measured C0
bootstrap/probe payload consumed by Granite; it is not a compositor, greeter,
session, or desktop environment.
There is no alternate desktop in the release image.

Calamares owns interaction and delegates Arach-specific mutations to a
transaction engine. Before any transaction or partition mutation, the
`arachhardware@preflight` job runs the live `/system/arach-hwd` scanner and
the signed `/etc/arach/hwd` catalog. It writes the discovery report to
`/run/arach-installer/hardware.toml` and the exact Corinth hardware plan to
`/run/arach-installer/hardware.plan.toml`. Every present physical capability
must resolve to a compatible signed profile; unresolved modaliases, missing
signatures, or an incompatible Driver ABI are hard stops rather than guessed
package choices. The reviewed
installer baseline is Calamares 3.4.2 from
`https://codeberg.org/Calamares/calamares.git`, peeled to Git object
`36d30c492e5c7b5d6d32fed5c5d9790522e1eea3`. The engine produces a complete
plan before changing disk state and writes a recovery journal before the first
destructive operation.

The catalog includes a signed hardware binary index as well as profiles.
Corinth uses the binary index for exact driver/firmware payloads when available
and otherwise builds the signed profile's pinned recipe. This makes Wi-Fi,
audio, graphics, storage, Bluetooth, and input provisioning use one
reproducible, rollback-safe path instead of assuming a package name from a
capability class.

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
same rollback immediately.

The live medium supplies `/run/arach-live/boot-bundle`, containing a bounded
`manifest.json` and four measured files: `granite.efi`, `arach`, `push`, and
the C0 probe in the compatibility slot named `crest`. That probe is not a
desktop image. `prepare` binds the exact manifest bytes to the immutable plan.
`apply` verifies every artifact, atomically installs Granite at
`/boot/EFI/BOOT/BOOTX64.EFI` and the three measured payloads under `/boot/BOOT`,
and retains backups in the target recovery checkpoint. `verify` re-hashes the
installed files; rollback restores the previous boot files, including after a
process or machine interruption. Artifact deployment is implemented, while the
complete live ISO and bounded QEMU/C0 session qualification remain release
gates.

Image assembly should use `scripts/assemble-boot-bundle.sh`; it rejects
symlinks, oversized or incorrectly typed artifacts, writes the canonical JSON
manifest, and publishes the directory only after all files and the manifest
have been synchronized.

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

The live medium is assembled in four bounded stages. First,
`scripts/materialize-live-system.sh` consumes the versioned Corinth artifact
directories described by `live/system.toml`, creates the `/system` and `/usr`
runtime paths, and records `/run/arach-live/system.json`. Next,
`scripts/assemble-boot-bundle.sh` creates the manifest-bound Granite/Arach/
Push/C0 directory. Finally, `scripts/assemble-live-root.sh` consumes the
materialized root, that boot bundle, and the signed Corinth generation. It
publishes the exact `/run/arach-live/system.json`,
`/run/arach-live/boot-bundle`, and `/run/arach-live/repository/system.gen`
paths only when every required Push/COSMIC/Calamares executable in
`live/image.toml` is present—including `greetd`, the COSMIC greetd config, and
the complete COSMIC component tree—and records the resulting root in
`/run/arach-live/image.json`. Finally, `scripts/build-live-iso.sh` invokes
xorriso with the measured Granite EFI path and `/BOOT` artifacts; it returns
status 69 when the ISO tool is unavailable and never publishes a partial ISO.
