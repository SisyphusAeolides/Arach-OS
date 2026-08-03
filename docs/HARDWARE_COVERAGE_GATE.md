# Hardware and driver coverage gate

This gate expands kernel and userspace driver coverage beyond baseline installer checks.

## Core coverage classes

1. ACPI and platform firmware handoff
2. PCIe enumeration and resource handoff
3. IOMMU and DMA boundaries
4. Storage controllers, NVMe/SATA/eMMC, and resume after suspend
5. USB host/device compatibility and hot-plug
6. DRM/KMS paths and display mode handling
7. evdev input parity
8. ALSA/SOF audio paths
9. Wi‑Fi/Bluetooth transport coverage
10. Webcam and media-class devices
11. Battery/power/thermal telemetry
12. Docking and external display flows
13. Suspend/resume and hibernation

## Bounded Linux compatibility fallback

- For unsupported native drivers, verify a bounded compatibility layer path exists
  before declaring broader compatibility.
- fallback implementations must include measurable resource and behavior constraints.

## Coverage evidence

- per-model smoke + stress logs
- driver resolution trace
- rollback or compatibility-route evidence where native paths are not available

## Completed bounded implementation scope

The implementation portion of this gate is complete and enforced across the
ArachOS integration graph:

- Arach-HWD records exact bus, modalias, module, firmware, target-kernel, and
  source-table provenance before it can emit a plan.
- Signed profiles bind the device identity, Driver ABI, package intent,
  firmware digest, health checks, rollback policy, and any closed compiler
  feature policy.
- Corinth accepts only the signed HWD plan and the signed package index or the
  pinned Arach-Packages recipe; unresolved hardware fails closed.
- Installer preflight compares live and target-kernel evidence and rejects a
  live-kernel binding that is absent from the target profile.
- Native-driver, rebuilt-driver, and bounded compatibility routes are distinct
  and measured; none is silently promoted to universal support.

The remaining qualification work is evidence collection on representative
physical systems for each matrix class, including suspend/resume, hot-plug,
firmware, power, display, audio, networking, and rollback behavior. QEMU,
static matrix fixtures, and CI success do not substitute for that evidence.

## Current status

`in_progress`  
Primary matrix and fallback policy are now explicit.
