# ArachOS ArchISO production profile

This profile builds the production ArachOS release path: Arch Linux packages,
the signed Sisyphus repository, KDE Plasma by default, and Calamares choices
for KDE Plasma, GNOME, COSMIC, GRUB, and systemd-boot. Limine is intentionally
absent until its install, update, and rollback contract is qualified.

Build only with `build.sh`. It refuses to build without an immutable version,
a complete signed Arach-HWD catalog, and a signed Pacman payload snapshot:

```sh
ARACHOS_ISO_VERSION=2026.08.05.1 \
ARACHOS_ISO_OUTPUT=/absolute/output \
ARACH_HWD_CATALOG_ROOT=/absolute/signed-hwd-catalog \
ARACH_HWD_PACMAN_SNAPSHOT_ROOT=/absolute/signed-pacman-hardware-snapshot \
./archiso/build.sh
```

`ARACH_HWD_CATALOG_ROOT` must contain the signed `keys.toml`, `catalog.lock`,
package index, driver ABI, profiles, and target-kernel driver evidence.
`ARACH_HWD_PACMAN_SNAPSHOT_ROOT` must contain the signed, plan-bound mapping,
its keyring, the exact Pacman configuration, and package archives. The build
script embeds them only after checking that all required inputs are regular
files or real directories.

The package lock must be checked before release promotion:

```sh
python3 scripts/verify_archiso_qualification.py \
  --package-lock /absolute/path/archiso-package-lock.json \
  --artifacts-root /absolute/path/archiso-artifacts
```

This validates the complete profile contract: Calamares module wiring and
order, enabled Arach-HWD and signed Pacman adapters, required signed build
inputs, pinned repository-key policy, and exact desktop/bootloader choices.
KDE is the default; GNOME and COSMIC are the only alternate desktop choices;
GRUB and systemd-boot are the only bootloader choices. The signed immutable
snapshot must contain the exact direct packages for every choice. In
particular, COSMIC cannot be promoted if `cosmic-session`, `cosmic-comp`,
`cosmic-greeter`, or `xdg-desktop-portal-cosmic` is absent. Package sources and
installer configuration must never use the AUR. Limine remains experimental,
absent from the Calamares choices, and unavailable to a production
installation.

Optional QEMU evidence is structural only: the validator requires retained
hash-bound image, OVMF, and scenario logs, then states that it does not claim
real QEMU or hardware qualification. Never interpret it as a qualification
claim unless a real harness produced and retained the reviewed evidence.
