# Security qualification gate

Production security qualification requires repeatable, evidence-first controls
around design, hardening, and response workflow.

## Required controls

1. Threat models:
   - document trust boundaries for installer, kernel, package supply chain, and runtime services.
2. Fuzzing:
   - continuous differential and regression-focused fuzzing where interfaces are exposed.
3. Hardening:
   - ASLR/W^X/stack hardening/SMEP/SMAP/IOMMU policy checks.
4. Privilege separation:
   - explicit process role boundaries and minimal secret lifetime.
5. Sandboxing strategy:
   - application runtime isolation with measurable policy and failure capture.
6. Key operations:
   - offline key storage for release signing
   - key rotation and revocation exercise
7. SBOM and attestations:
   - reproducible artifact manifest
8. Reproducibility:
   - independent build replication and artifact comparison
9. Vulnerability intake:
   - intake queue, triage time, and patch rollout SLA

## Evidence to retain

- gating artifacts (build hashes, SBOM, attestations)
- threat-model revision history
- patch drill logs (rotation/revocation and vuln response)
- security regressions with explicit severity and rollback actions

## Current status

`in_progress`  
Control set formalized and ready for enforcement rollout.
