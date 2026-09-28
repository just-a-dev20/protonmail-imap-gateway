# Security reporting

Do not post credentials, message content, or exploitable private account details in public issues. Use this repository's GitHub Security → Report a vulnerability if private vulnerability reporting is enabled. If unavailable, open an issue asking the maintainer to provide a private reporting channel, without vulnerability details.

This is an initial release with no independent security audit or response-time guarantee. Only the latest source revision is maintained. Read [the threat model](docs/security.md). Revoke exposed Proton sessions and local client credentials immediately; deleting a log does not revoke them.
