# Linux application compatibility tiers gate

Route each workload through the most appropriate path and track transitions.

## Compatibility tiers

1. native compatible
2. rebuilt from source
3. compatibility runtime
4. managed OCI container
5. managed Linux VM fallback

## Core parity checks

- glibc/musl ABI and libc coverage
- FHS path semantics and interpreter behavior
- ELF interpreter and dynamic loader behavior
- syscall coverage with bounded unsupported-path controls
- ioctl compatibility and driver-dependent boundaries

## Route evidence

- package-level routing decision recorded with fallback reason
- success/failure by workload class
- measurable migration path when native path is not possible

## Current status

`complete`  
Tier matrix is now explicit; runtime route evidence is implemented and enforced.
