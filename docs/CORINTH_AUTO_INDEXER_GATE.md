# Automatic Corinth repository service gate

Goal: make recipe/source tracking continuously reproducible and resilient.

## Indexer services

Each upstream family must run as a persistent indexer with immutable revision capture:

- Arch/AUR
- Fedora
- Debian
- Alpine
- Gentoo
- CRUX
- Nix
- Cargo
- GitHub

## Required behavior

- resolve immutable revisions
- generate canonical recipe metadata
- build/update dependency closure deterministically
- sign and publish catalog artifacts
- handle upstream removal or compromise without breaking consumers

## Evidence requirements

- per-source timestamped ingestion manifests
- signed catalog diffs
- reproducibility checks
- incident response runbook (revocation/removal/rollback)

## Current status

`done`
Service responsibilities are now explicit and implemented.
