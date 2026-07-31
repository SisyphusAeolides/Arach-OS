# Arach OS installer integration

The installer configuration targets Calamares 3.4.2 at the exact peeled Git
object recorded in `contract.toml`. The COSMIC live session installs the
canonical Arach branding asset into the Calamares branding directory according
to the measured asset mapping in that contract.

The live session uses `greetd` with the pinned `seatd`, PipeWire, and
WirePlumber runtime services plus the pinned COSMIC
`/etc/greetd/cosmic-greeter.toml` configuration; SDDM is intentionally not a
runtime dependency. The complete COSMIC install tree, greeter launcher,
terminal, portal, and display-manager binary are required before the image is
published.

The hardware catalog is equally complete at the discovery boundary. Its lock
ships signed profile/index data plus hashed `modules.alias`, `modules.dep`,
`modules.builtin`, and `modules.firmware` snapshots under
`/etc/arach/hwd/driver-sources`. Calamares feeds those exact tables to
`arach-hwd` before it considers live, target, or offline module roots, so
Wi-Fi, audio, graphics, storage, input, Bluetooth, and firmware lookup is
reproducible for the target rather than dependent on the temporary live
kernel.

The external `arachtransaction` module has two instances. `prepare` runs before
the partition job and requires `arach-install` to create the immutable plan and
recovery journal. `commit` runs after the root filesystem has been mounted and
unpacked; it applies and verifies the plan, invoking rollback on failure.

Calamares retains user and root passwords and the LUKS passphrase. The
transaction handoff is an allowlist and never reads or serializes those keys. It
invokes binaries with argument arrays and never through a shell.

`arach-install prepare` validates the private state document and Corinth
generation, then binds both to a private canonical plan and SHA-256 journal.
It also binds the SHA-256 of the live boot-bundle manifest. Apply persists a
second recovery bundle under the mounted target before it publishes Corinth
authority, then atomically installs the manifest-verified Granite, Arach, Push,
and C0 probe artifacts into the EFI layout. The C0 probe is stored under the
legacy `crest` boot slot and is not a desktop environment. Verify re-hashes
those files, and
Calamares rolls both boot files and Corinth authority back on failure; after a
restart, `arach-install recover --target <root>` performs the same recovery
from the target bundle. The complete live ISO and bounded QEMU/C0 session gate
remain separate release work.

The production native-COSMIC bundle contains the complete measured service
set: `seatd`, `dbus-broker`, `pipewire`, `wireplumber`, `cosmic-comp`,
`cosmic-greeter`, `cosmic-session`, and `xdg-desktop-portal-cosmic`. The
installer accepts this set only when all eight ELF files and all eight manifest
digests are present; partial sets are rejected. The C0-only four-artifact
bundle remains valid for the compatibility qualification path.

The boot bundle directory is fixed and contains:

```text
manifest.json       # schema = 1, four base fields plus eight COSMIC fields
granite.efi         # PE/COFF UEFI image
arach               # ELF kernel image
push                # ELF PID 1 image
crest               # ELF measured C0 bootstrap/probe image; not a desktop
seatd               # native COSMIC seat/session permission service
dbus-broker         # native COSMIC D-Bus service
pipewire            # native COSMIC audio/video service
wireplumber         # native COSMIC session manager
cosmic-comp         # native COSMIC compositor
cosmic-greeter      # native COSMIC greeter
cosmic-session      # native COSMIC session
xdg-desktop-portal-cosmic # native COSMIC portal
```
