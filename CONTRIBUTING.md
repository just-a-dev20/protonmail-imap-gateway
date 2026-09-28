# Contributing

Contributions are licensed GPL-3.0-or-later. Keep security fixes focused, with regression tests. Never attach live credentials, real messages, session dumps or unredacted upstream logs.

Run the test and lint commands in README. Python runtime dependencies are standard-library only. Protocol tests use TLS mock backends and verify transport, authentication boundaries and limits; they do not verify actual Proton delivery or mailbox semantics. Keychain tests exercise encryption, nonces, integrity, incorrect keys and CRUD using the actual adapter source. Add real-client results only with explicit test evidence and no private data.

Upstream upgrades must update the exact Dockerfile revision and protocol research, inspect all patches, check API entitlements, run the build and vulnerability scan, and test interactive setup with a consenting paid test account. Do not change the client identity to access another product's entitlement. Do not remove certificate verification to fix TLS tests.

No binaries or secret material belong in git. Images must retain corresponding source and dependency licenses. Changes to encryption need independent review; use maintained libraries and avoid custom primitives.
