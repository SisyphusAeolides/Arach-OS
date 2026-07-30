# Package and source architecture

Corinth separates source availability from installation authority.

## Repositories

1. **Arach-Packages** contains source recipes, patchsets, licenses, dependency
   constraints, hardware matches, and immutable source locks.
2. The **Arach build service** executes recipes in clean, network-isolated
   builders after all locked sources are fetched and measured.
3. The **Arach native repository** publishes signed binary packages, source
   manifests, software bills of materials, build attestations, and deltas.
4. The **Arach hardware index** publishes signed device-to-driver and
   device-to-firmware mappings consumed by Arach-HWD.

## Source providers

- crates.io sparse registry for locked Rust source packages;
- immutable upstream Git revisions and signed release archives;
- local and removable-media mirrors for offline installation;
- OCI transport for signed native repository snapshots;
- approved vendor and upstream firmware ingested with license metadata.

Raw crates.io and Git inputs may produce user or build artifacts, but they
cannot directly authorize a system driver. System packages require the signed
Arach native repository. Drivers and firmware additionally require a matching
signed Arach hardware profile and compatible Arach Driver ABI.

## Channels

The repository will publish `unstable`, `testing`, and `stable` snapshots per
architecture. Promotion copies content-addressed objects without rebuilding
them and signs a new snapshot only after the complete boot, installer,
hardware, rollback, and COSMIC desktop gates pass.
