# Release integrity and promotion gate

This gate is the release-blocking boundary for a candidate moving from
development through testing to stable. It prevents a green build, an isolated
test result, or a single signed package from being mistaken for a releasable
ArachOS image.

## Immutable release inputs

- `components.lock.toml` must resolve every component to a full immutable Git
  object ID, and `scripts/verify-components.py --remote` must confirm that the
  pinned objects and nested Arach-Packages recipes are available.
- The Corinth package generation, boot bundle, image manifest, ISO digest, and
  signature must all be bound to the same release record.
- The retained release report must include a copy of the exact component lock
  whose SHA-256 appears in the release record. A later lock update cannot
  retroactively change an already promoted image.

## Required release evidence

Before qualification, retain revision-bound, SHA-256-verified evidence for:

1. two independent image builds with matching image and boot-bundle digests;
2. an SBOM and signed provenance/attestation for the candidate;
3. CI build, install, update, and rollback results;
4. a successful rollback drill from the candidate on the supported channel;
5. release notes and an advisory record describing scope, known limitations,
   and rollback instructions; and
6. mirror publication and quorum verification for the immutable snapshot.

Evidence that is marked mock, placeholder, synthetic, sample, or example is
never qualification evidence.

## Promotion rules

1. A development record may be published directly only with retained release
   evidence.
2. Testing and stable records must identify a retained record in the preceding
   channel.
3. Promotion must preserve the release revision, component-lock digest,
   package-generation digest, image digest, and signature digest exactly.
4. Stable requires all fourteen production-readiness gates, including this
   gate, to be qualified. It cannot bypass a hardware, security, recovery, or
   compatibility blocker.
5. A promotion record must meet the channel soak, mirror quorum, advisory, and
   rollback requirements in `production/release-channels.json`.

The validators enforce the record format and immutable promotion relationship;
they do not substitute for the real evidence listed above.

## Current status

`in_progress`

The policy and validation path are defined, but no release candidate has yet
supplied the complete retained evidence required for qualification.
