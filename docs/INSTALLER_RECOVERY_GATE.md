# Installer and recovery certification gate

This gate covers the installer/recovery workflows that are not yet fully automated in
CI and need repeatable evidence before full production claims.

## Required scenarios

1. clean install
2. reinstall onto existing Arach partition
3. dual-boot preservation checks
4. encrypted storage create/unlock
5. TPM-backed recovery path where present
6. Secure Boot + signed-boot path
7. interrupted partitioning rollback
8. disk-full safeguards
9. corrupted cache handling
10. power-loss during activation
11. failed-kernel rollback path
12. rescue/repair media path
13. major-version in-place upgrade

## Evidence requirements per scenario

- exact catalog/plan hash before mutation
- immutable transaction journal entry for each transition
- explicit failure mode classification (rollback-success, resume-possible, manual
  intervention required)
- post-recovery bootability and COSMIC launch check

## Runtime markers

The same live-ISO gate supports optional checkpoints via:

- `ARACH_LIVE_SESSION_MARKERS` / `ARACH_LIVE_SESSION_MARKERS_FILE`
- `ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS` / `ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS_FILE`
- optional `ARACH_LIVE_MARKER_REPORT`

Use this to capture additional installer and recovery phase transitions whenever they
become observable in serial logs.

## Current status

`in_progress`
The scenarios and validation contract are defined, but each scenario still
needs real revision-bound installer and recovery evidence before qualification.
