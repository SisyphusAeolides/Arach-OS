# Dynamic compatibility workers gate

This gate defines the replacement path for complex package build pipelines that
cannot be represented as static source metadata alone.

## Worker classes

1. PKGBUILD worker
2. spec/deb/rules worker
3. Gentoo ebuild worker
4. custom setup/build-script worker
5. source-bundle normalizer worker

Each worker class must run in a dedicated capability boundary with:

- declared resource permissions (filesystem/network/keys)
- deterministic input snapshots
- measured output receipts (build logs, receipts, diff summaries)
- reproducibility verification against a second run window
- strict timeout and kill policy

## Compatibility policy

- never run unrestricted host network from untrusted recipes
- prefer source-of-record manifests and pinned revisions
- preserve exact user intent and error semantics
- emit explicit failure classes:
  - `metadata_parse`
  - `sandbox_violation`
  - `non_deterministic_output`
  - `upstream_removal`
  - `security_violation`

## Evidence

- per-worker manifest
- sandbox policy snapshot
- reproducibility delta report
- rejection rationale for unsupported features

## Current status

`in_progress`  
Worker classes are specified and bounded, ready for staged implementation.
