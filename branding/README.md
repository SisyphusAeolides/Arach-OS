# Arach visual identity

`arach-logo.png` is the canonical distribution mark. It is byte-identical to
the supplied source artwork and has SHA-256 digest:

```text
87cc9d21c92c1cfd648e316e3e22e2961b644d375eec21c4ded1c0afc1de5a6e
```

All boot, live-session, installer, greeter, desktop, documentation, and release
derivatives must be generated from this file. Generated sizes belong under
`branding/generated/`; they must not replace the canonical source.

## Current ArachOS integration status

This project is maintained as part of the ArachOS production graph. Its role is
the immutable distribution branding inputs used by release verification..

CI and release evidence are evaluated on immutable revisions. Hardware support
is reported by bounded route and support level; this README does not claim
universal native support. Gate 3 requires signed hardware identity, target
kernel provenance, package authority, health checks, rollback behavior, and
representative physical-hardware evidence before production qualification.
