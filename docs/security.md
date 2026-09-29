# Security design and threat model

The storage, vault and certificate-export details below describe the default **official Bridge mode**. The experimental Hydroxide mode shares the network/process controls but uses different credential encryption and an unencrypted mailbox metadata database; see [web-backend security differences](web-backend.md#storage-and-security-differences). Its generated client password is independent of official Bridge.

## Boundaries and stored data

Proton authentication, mailbox-key handling and OpenPGP stay in the upstream engine. Passwords are entered into its interactive terminal with its hidden-input handling. The gateway accepts only Bridge-generated mail-client credentials; Proton session tokens never become client credentials. No password environment variable is provided.

The Linux keychain adapter seals its complete credential map using Go's standard-library AES-256-GCM, a fresh random 96-bit nonce, and versioned authenticated data. A 32-byte random key is supplied as a Docker secret outside the data volume. Reads authenticate before JSON parsing. Writes take a process lock, use a mode-0600 temporary file, fsync, atomic rename and directory fsync. Temporary decrypted byte buffers are zeroed where practical; Go/Python garbage collectors and copies do not guarantee erasure. The keychain protects the key used by Bridge's own vault. The upstream insecure-vault fallback is disabled: keychain errors stop startup. Bridge retains its encrypted cache and its ordinary metadata/database files on the persistent volume; **this is not whole-volume encryption**. Use host/disk encryption if metadata exposure matters.

The TLS private key for the public listener is a separate Docker secret. Setup temporarily exports the backend TLS key along with its certificate, then deletes the exported key on exit; interrupted setup can leave that export in the volume. The public backend certificate is retained to validate backend TLS, including its 127.0.0.1 SAN. Trust checks are never disabled. A stolen volume plus its master secret defeats vault confidentiality. Copying Docker secrets alongside volume backups defeats the intended separation.

## Network and process controls

Only implicit TLS is exposed (IMAPS and SMTP submission over TLS); minimum TLS 1.2. Host ports bind to 127.0.0.1 by default. Compose explicitly enables 0.0.0.0 *inside its network namespace* for NAT, so other containers on the same Compose network may connect. LAN publishing requires editing the host port bindings and provisioning a certificate for the chosen hostname. Do not publish the health port or use host networking. Prefer a firewall/VPN for remote clients.

The default global budget is 20 new connections/minute, with one authentication attempt per connection, a 64-line pre-authentication budget, a 60-second login deadline and a one-hour absolute session lifetime. Wrong IMAP authentication or malformed tagged commands and SMTP authentication errors close the connection. Pipelined repeated authentication commands are rejected. The global budget is deliberately not indexed by attacker-controlled addresses and resists rotating-IP evasion, but can deny legitimate clients during an attack. It resets on restart. These limits apply after the TLS handshake; firewall controls are needed against handshake-level floods. Python buffers and socket backpressure bound ordinary relay memory, and Compose bounds container memory and PIDs.

The service runs as UID 10001, drops all Linux capabilities, disables core dumps, uses no-new-privileges, a read-only root filesystem and a constrained tmpfs. A file lock prevents concurrent setup and serving against the same volume. SIGTERM stops listeners and Bridge. Client sessions expire independently of Proton sessions; upstream may refresh Proton tokens indefinitely. Revoke a stolen Proton session through Proton's account security settings, then re-run setup. There is no custom token TTL or unattended credential rotation.

## Logs and observability

Bridge source contains logs of human-verification tokens, so this build discards its logrus output and hooks, including during setup. Runtime child stdout/stderr are discarded. Gateway logs contain fixed event names and severity only, never exception text, peer addresses, usernames, protocol frames, tokens or message bodies. The event-loop exception handler also emits a fixed event. Setup intentionally displays account credentials through the upstream `info` command and may display a human-verification URL: treat terminal scrollback as sensitive and do not record it. Do not enable upstream debug/protocol logging. Upstream crash paths can produce stack diagnostics; these are not a forensic redaction guarantee after arbitrary runtime compromise.

The loopback-only health endpoint probes TLS greetings. It reports Proton session and sync state as unknown; there is no management UI, message counter, body browser, or reconnect web endpoint.

## Threats

| Threat | Mitigation | Residual risk |
|---|---|---|
| Compromised LAN device | Loopback publishing; explicit LAN setup; validated TLS; authentication | DoS, stolen client password, mistakes in firewall configuration |
| Malicious IMAP/SMTP client | Upstream parsers, pre-auth limits, bounded lifetime, container limits | Authenticated clients can read/delete/send as the account; upstream vulnerabilities |
| Stolen Docker volume | External master key, AEAD-protected keychain and upstream vault/cache | Metadata leakage; rollback/deletion attacks; all protection lost if keys are stolen too |
| Malicious same-host container | Separate namespaces, no Docker socket mount, credentials and TLS | Same-network connection attempts; host/kernel exploits; shared secrets misconfiguration |
| Compromised reverse proxy | Direct TLS is recommended; no web management | A TLS-terminating proxy can steal mail credentials and plaintext mail |
| Stolen Proton session | Upstream session revocation, reauthentication | Valid stolen tokens/keys may grant account access until revoked |
| Memory compromise | Short-lived buffers, no core dumps, least privilege | Running engine necessarily holds plaintext mail, keys and tokens; no protection against process memory access |
| Compromised Docker host | None sufficient within a container | Root/Docker administrators can read secrets, RAM and client data; rebuild and revoke credentials |

The gateway moves a decryption endpoint onto your server. It cannot protect mail from that server's administrator or a compromised host, nor secure copies downloaded by email clients. It is not security-audited. Protect backups, keep upstream/base images updated, and audit before production use.
