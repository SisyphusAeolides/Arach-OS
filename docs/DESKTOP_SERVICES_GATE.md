# Desktop services production gate

This gate covers the runtime services stack expected for production COSMIC usability.

## Required service coverage

Each service area below needs evidence from:
- QEMU smoke path where practical, and
- at least one targeted hardware validation run where signals are stable.

1. Networking (system-wide)
   - route/hostname/DNS functional baseline
   - offline/online transitions
2. Wi‑Fi authentication and secrets workflow
   - connect/disconnect with enterprise/user credentials in a controlled profile
3. Time synchronization
   - periodic wall-clock convergence and signed source trust chain
4. D-Bus
   - service bus continuity under startup/shutdown
5. Portals
   - desktop portal invocation path exercised by one representative app
6. Audio and Bluetooth audio
7. Credentials and authorization
   - account lifecycle and privilege boundary checks
8. Printing and removable media
9. Camera stack
10. Notification stack
11. Update and diagnostics channels
12. Locale and font stack
13. Input methods and accessibility hooks
14. Power management (suspend/resume/reconnect)

## Acceptance checkpoints

- Service definitions are pinned to known-good versions in the image manifest.
- Unit-level checks run in the image CI suite; integration checks run at runtime.
- No service silently restarts before bounded startup timeout.
- Regressions are annotated with explicit failure class:
  - `blocked_by_driver`, `driver_incompatibility`, `missing_coverage`,
    `intermittent_hardware`, `service_contract_broken`.

## Evidence artifacts

- runtime markers captured by `scripts/experimental-native-run-live-iso-qemu.sh`
- service state snapshots during installer and post-boot sessions
- failure logs + rollback evidence when coverage probes fail

## Current status

`in_progress`
The initial acceptance matrix exists, but implementation and evidence capture
remain incomplete.
