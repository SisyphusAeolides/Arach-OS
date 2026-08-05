# Future ArchISO package and QEMU qualification

This validates the retained inputs for the ArchISO production profile. The
profile is built only through `archiso/build.sh`, which requires an immutable
release version, a complete signed Arach-HWD catalog, and the exact signed
Pacman hardware payload snapshot. It does not publish Sisyphus-Repo content or
make a release-qualified claim by itself.

## Immutable signed inputs

Create an `archiso-package-lock.json` and an artifact directory after package
selection, signature verification, SBOM generation, and provenance generation.
Run:

```sh
python3 scripts/verify_archiso_qualification.py \
  --package-lock /absolute/path/archiso-package-lock.json \
  --artifacts-root /absolute/path/archiso-artifacts
```

The JSON object has these exact top-level fields:

```json
{
  "format": 1,
  "distribution": "ArachOS",
  "archiso_profile_revision": "<40-or-64-hex Git ID>",
  "snapshot": {
    "id": "20260805.1",
    "repository": "https://packages.example/snapshots/20260805.1",
    "generated_at": "2026-08-05T18:00:00Z",
    "database": {
      "path": "sources/core.db",
      "sha256": "<sha256>",
      "signature": "sources/core.db.sig",
      "signature_sha256": "<sha256>",
      "signer_fingerprint": "<40-or-64-uppercase-hex>"
    },
    "keyring": {"path": "keys/archiso.gpg", "sha256": "<sha256>"},
    "verification": {
      "path": "verification/core-db.gpgv.txt",
      "sha256": "<sha256>",
      "tool": "gpgv"
    }
  },
  "packages": [
    {
      "name": "example",
      "version": "1.0-1",
      "architecture": "x86_64",
      "repository": "https://packages.example/snapshots/20260805.1",
      "archive": {
        "path": "packages/example-1.0-1-x86_64.pkg.tar.zst",
        "sha256": "<sha256>",
        "signature": "packages/example-1.0-1-x86_64.pkg.tar.zst.sig",
        "signature_sha256": "<sha256>",
        "signer_fingerprint": "<40-or-64-uppercase-hex>"
      }
    }
  ],
  "package_set_sha256": "<canonical JSON SHA-256 of packages>",
  "sbom": {
    "path": "metadata/image.spdx.json",
    "sha256": "<sha256>",
    "format": "spdx-json",
    "package_set_sha256": "<package_set_sha256>"
  },
  "provenance": {
    "path": "metadata/image.intoto.json",
    "sha256": "<sha256>",
    "format": "in-toto-statement",
    "package_set_sha256": "<package_set_sha256>"
  }
}
```

`package_set_sha256` is SHA-256 of the UTF-8 JSON encoding of `packages` with
keys sorted and separators `,` and `:`. The verifier requires retained regular files, matching hashes, HTTPS source
identity, detached signatures, a pinned keyring, an immutable profile
revision, and valid JSON SBOM/provenance evidence. The SBOM must enumerate the
same names and versions as the locked packages; the in-toto statement must
include its `predicate`, `predicateType`, and an `arachos-package-set` subject
with the package-set digest. It does not execute signature tools: the
verification transcript must be produced by a trusted `gpgv` or `pacman-key`
step before this structural verifier is run.

It also validates the checked-in ArchISO contract: exact Calamares module
wiring and ordering; the enabled Arach-HWD and signed Pacman adapters; required
signed HWD catalog and Pacman snapshot build inputs; the pinned Sisyphus key
policy; and exact choice sets. KDE Plasma is the default; GNOME and COSMIC are
the selectable desktops; GRUB and systemd-boot are the only bootloader choices.
The immutable signed snapshot must contain the direct KDE, GNOME, COSMIC, GRUB,
and systemd-boot package sets. A missing COSMIC package rejects promotion
rather than falling back to the AUR; AUR endpoints are rejected outright.
Limine is experimental only and must not appear in the production profile.

## QEMU install lifecycle evidence

After a real QEMU/OVMF harness has booted the ISO and performed installation,
write a report plus logs and image into a separate retained artifact directory:

```sh
python3 scripts/verify_archiso_qualification.py \
  --package-lock /absolute/path/archiso-package-lock.json \
  --artifacts-root /absolute/path/archiso-artifacts \
  --qemu-report /absolute/path/qemu-qualification.json \
  --qemu-artifacts-root /absolute/path/qemu-artifacts
```

The report binds the exact raw lock-file SHA-256 and ISO SHA-256. It records a
`q35` QEMU binary/version and OVMF digest, then contains these ordered passed
scenarios: `live-boot`, `install`, `reboot-installed`, `update`, and
`rollback`. Each contains a hash-bound regular serial/console log and these
fields:

```json
{
  "format": 1,
  "captured_at": "2026-08-05T18:15:00Z",
  "package_lock_sha256": "<raw lock file sha256>",
  "image": "images/arachos.iso",
  "image_sha256": "<sha256>",
  "qemu": {
    "binary": "qemu-system-x86_64",
    "version": "<version>",
    "machine": "q35",
    "firmware_sha256": "<OVMF sha256>"
  },
  "firmware": {
    "path": "firmware/OVMF_CODE.fd",
    "sha256": "<OVMF sha256>"
  },
  "initial_snapshot_sha256": "<lock snapshot database sha256>",
  "update_snapshot_sha256": "<different update snapshot sha256>",
  "scenarios": [{
    "id": "rollback",
    "status": "passed",
    "log": "logs/rollback.log",
    "log_sha256": "<sha256>",
    "snapshot_before_sha256": "<update snapshot sha256>",
    "snapshot_after_sha256": "<initial snapshot sha256>",
    "post_reboot": true
  }]
}
```

The verifier rejects skipped lifecycle phases, failed status, a non-`q35`
machine, absent retained OVMF firmware, changes to the initial package snapshot
during install/reboot, an update that does not move to a distinct snapshot, and
a rollback that does not restore the original snapshot after reboot. Passing
this gate only validates retained evidence structure and hashes. Its output
explicitly does not claim real QEMU or hardware qualification; that claim
requires review of evidence genuinely produced by the real harness.
