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
Apply persists a second recovery bundle under the mounted target before it
publishes Corinth authority. Calamares rolls that authority back on failure;
after a restart, `arach-install recover --target <root>` performs the same
recovery from the target bundle. Apply still returns unavailable at the
unimplemented package-artifact and Granite activation boundary. This is an
intentional release gate, not a successful installation path.
