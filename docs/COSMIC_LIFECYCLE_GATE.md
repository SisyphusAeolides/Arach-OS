# COSMIC lifecycle gate evidence plan

This document tracks the concrete evidence needed to close the Full COSMIC lifecycle
gate in production readiness.

## Scope

Required end-to-end sequence under installer and hardware validation:

1. install
2. reboot
3. greetd start
4. login/session handoff
5. usable desktop session
6. suspend
7. resume
8. logout
9. shutdown
10. post-reboot artifact and recovery integrity check

## QEMU execution evidence

`scripts/run-live-iso-qemu.sh` currently validates boot-to-service milestones.
It can be extended incrementally with optional session markers:

- set `ARACH_LIVE_SESSION_MARKERS` (newline-separated regexes), or
- set `ARACH_LIVE_SESSION_MARKERS_FILE` with comment-capable newline-separated
  regexes.

For lifecycle sequencing beyond initial login, use a dedicated file:

- set `ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS` (newline-separated regexes), or
- set `ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS_FILE`.

Example:

```sh
ARACH_LIVE_COSMIC_LIFECYCLE_MARKERS_FILE="$PWD/docs/COSMIC_LIFECYCLE_MARKERS.sample" \
  scripts/run-live-iso-qemu.sh /absolute/path/to/arach-os-c0.iso /tmp/arach-os-c0.serial.log
```

See [`docs/COSMIC_LIFECYCLE_MARKERS.sample`](COSMIC_LIFECYCLE_MARKERS.sample)
for marker starter patterns.

Example marker file:

```text
# COSMIC lifecycle evidence examples
greetd.*requesting session
cosmic-session.*ready
```

The run exits non-zero if required markers are missing or out of sequence.

To retain a revision-bound lifecycle artifact, invoke the marker verifier with
`--evidence`, `--revision`, and either `--environment qemu` or
`--environment physical-hardware`. Evidence creation is non-overwriting and
records the serial-log SHA-256 plus the ordered marker locations.

## Production evidence matrix (not yet automated)

- Installer media and rollback checkpoints are currently validated in existing gates.
- Installer → reboot is currently covered by existing live ISO execution and tests.
- Suspend/resume, logout, and shutdown are pending evidence capture and are intentionally
  explicit blockers for full gate completion.

This keeps the gate explicit, incremental, and CI-safe.

## Current status

`in_progress`

QEMU milestone validation is available, while complete ordered lifecycle
evidence from QEMU and representative physical hardware remains outstanding.
