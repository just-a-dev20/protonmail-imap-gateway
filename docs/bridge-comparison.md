# Comparison with official Proton Mail Bridge

| Area | Official Bridge | This project |
|---|---|---|
| Architecture | Desktop process, Gluon IMAP, SMTP, Proton API | Same pinned headless engine plus Python TLS transport/supervisor |
| Protocols | IMAP and SMTP, STARTTLS/SSL modes | Implicit TLS externally and internally; configurable ports |
| Authentication | Proton SRP/2FA/mailbox password; generated client password | Upstream interactive CLI; same credentials and entitlement rules |
| Encryption | Proton libraries and encrypted local cache | Same mail encryption; external-secret AES-GCM Linux keychain |
| Clients | Officially documented desktop integrations | Manual IMAP/SMTP configuration; no graphical client certified here |
| Docker | Desktop installation documented upstream | Non-root Compose, read-only root, secrets, capability drop, healthcheck |
| Logging | Upstream diagnostics and logs | Upstream logs suppressed; fixed structured gateway events |
| LAN | Designed for a local email client | Explicit host publishing and trusted TLS required; VPN recommended |
| Updates | Upstream update mechanisms | Rebuild and test pinned source; binary autoupdates disabled |
| Free plans | Not supported by Proton's Bridge documentation | Unsupported; no entitlement bypass |
| Management | Desktop UI and CLI | CLI only; loopback listener health, no sync dashboard |

The wrapper is an independent deployment layer, not an official Proton product or a new Proton protocol implementation. It does not extend account entitlements. Client and live-account verification remains separate from automated mock tests. See [protocol research](proton-protocol.md) for exact source revisions and references.
