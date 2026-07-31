# Arach OS installer integration

The installer configuration targets Calamares 3.4.2 at the exact peeled Git
object recorded in `contract.toml`. The COSMIC live session installs the
canonical Arach branding asset into the Calamares branding directory according
to the measured asset mapping in that contract.

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
and Crest artifacts into the EFI layout. Verify re-hashes those files, and
Calamares rolls both boot files and Corinth authority back on failure; after a
restart, `arach-install recover --target <root>` performs the same recovery
from the target bundle. The complete live ISO and bounded QEMU/C0 session gate
remain separate release work.

The boot bundle directory is fixed and contains:

```text
manifest.json       # schema = 1, four lowercase SHA-256 fields
granite.efi         # PE/COFF UEFI image
arach               # ELF kernel image
push                # ELF PID 1 image
crest               # ELF measured bootstrap/session image
```
