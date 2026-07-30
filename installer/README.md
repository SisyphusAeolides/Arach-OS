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

`arach-install prepare` validates the private state document, emits a canonical
plan, and binds it to a private recovery journal by SHA-256. Apply currently
fails with the unavailable status before touching the target because Corinth's
durable installation backend and Granite activation are not implemented. This
is an intentional release gate, not a successful installation path.
