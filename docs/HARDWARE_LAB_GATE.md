# Hardware lab and release operations gate

This gate formalizes how representative hardware coverage and channel operations are
validated before production claims.

## Matrix baseline

Coverage bands:

- **Certified**: pass full lifecycle + all required service probes on hardware class.
- **Compatible**: functional with documented caveats.
- **Experimental**: partial coverage; no guarantee for all listed operations.

Representative fleet classes to cover in CI-like cadence:

- Lenovo, Dell, HP, Acer systems
- AMD and Intel CPU platforms
- NVIDIA and integrated GPU graphics paths
- Wi‑Fi (802.11ac/ax), audio (HDMI/pipewire), storage (NVMe/SATA/NVMe-thermal),
  docks, USB-C alt modes, eGPU and USB hotplug
- ACPI suspend/resume, thermal throttling, battery transitions

## Release operations

Channel policy:

1. Stable channel with narrow promotion gates.
2. Testing channel for full gate and hardware matrix updates.
3. Development channel for fast iteration and rollback drills.

Required operational artifacts:

- mirrored package/feed endpoints
- published support matrix with status for each model class
- advisories + vulnerability intake workflow
- controlled rollback drills for package and kernel badness
- release notes that include known caveats for each channel

## Reproducibility and audit

- Build artifacts must retain immutable generation metadata and lock IDs.
- Soak tests must run on at least one stable candidate before broad promotion.
- Any release block for compatibility regression triggers automatic freeze until resolved.

## Current status

`in_progress`  
This is now tracked as explicit release-operational acceptance criteria.
