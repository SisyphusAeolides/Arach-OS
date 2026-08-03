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

## Current status

`in_progress`  
Primary matrix and fallback policy are now explicit.
