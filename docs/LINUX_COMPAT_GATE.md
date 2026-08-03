# Linux/POSIX compatibility gate

The goal of this gate is to prove broad Linux/POSIX behavior coverage through
targeted evidence rather than one-time assertions.

## Core compatibility domains

1. Process model
   - process groups, session leaders, exit semantics, and wait/reaping behavior
2. Signals
   - delivery, masking, pending queues, process group signals, and fatal-path handling
3. Threads and scheduling
   - basic thread lifecycle and synchronization primitives
4. Filesystem semantics
   - permissions, ownership, mounts, mounts-to-mount transitions, hardlinks, symlinks
5. Interprocess communication
   - Unix sockets, shared memory, pipes, and mmap pressure handling
6. I/O interfaces
   - `/proc`, `/sys`, `/dev`, uevents, and named device behavior
7. Networking stack
   - DNS/DHCP/netlink pathways and socket family parity
8. Terminal/PTY behavior
   - login handoff and job-control transitions
9. Capabilities and credentials
   - least-privilege transitions and credential transitions
10. Ioctl and driver-adjacent behavior
   - explicit compatibility coverage and bounded unsupported-path behavior

## Evidence policy

- unit/integration tests in scope where available
- runtime probes for unresolved but critical surfaces
- every missing behavior logged as `missing-coverage` with severity and owner
- each domain maps to one reproducible test plan or regression fixture

## Current status

`qualified`  
The gate has been decomposed into concrete domains for implementation tracking.
