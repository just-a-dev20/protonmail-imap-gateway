# Proton Mail IMAP Gateway

A self-hosted Docker deployment layer for **paid Proton Mail accounts**, using the published Proton Mail Bridge engine for IMAP, SMTP, authentication, synchronization and encryption. Independent of Proton AG. GPL-3.0-or-later.

**Free accounts are unsupported.** Proton documents Bridge as a paid-plan feature. This project preserves account entitlement checks. It does not use web-client impersonation or bypass human verification.

Status: initial implementation. Account-free transport/security tests are provided. No real Proton account or graphical email client has been tested by this project. Do not treat mock protocol tests as certification of production mail delivery. See [validation](docs/validation.md).

## Architecture

```text
Thunderbird / Apple Mail / Outlook / mobile IMAP client
       | IMAPS :1993        | SMTP submission over TLS :1465
       +-------------------+
          Python TLS gateway
          connection limits / authentication deadline / session expiry
                    | verified TLS on container loopback
          Proton Mail Bridge (pinned source)
          Gluon IMAP / SMTP / Proton cryptography / sync
                    | HTTPS with certificate validation
                  Proton Mail
```

The gateway does not independently deliver internet mail. Bridge handles folders/labels, flags, read/unread, starred, drafts, sent, trash, spam, mailbox synchronization, and mail encryption. IMAP and SMTP are kept behind a socket interface so the wrapper has no Proton message-object dependency. The proxy preserves MIME payloads and IMAP literals. It inherits upstream limits on encryption, addresses, aliases, SMTPUTF8 and recipient policies; SMTPUTF8 is not promised.

## Compatibility

These entries reflect upstream documentation, **not live account tests here**. A paid plan must specifically include Mail Bridge; an unrelated Proton product subscription is not sufficient.

| Feature through this gateway | Proton Free | Bridge-eligible paid plan |
|---|---|---|
| Proton login for gateway use | Unsupported | Upstream supported; untested here |
| Read mail | Unsupported | Upstream supported; untested here |
| Send mail | Unsupported | Upstream supported; untested here |
| IMAP gateway | Unsupported | Implemented using Bridge; transport tested with mocks |
| SMTP gateway | Unsupported | Implemented using Bridge; transport tested with mocks |

Official Free webmail remains available through Proton's own applications. No Free-account functionality has been confirmed working in this gateway. [Proton's Linux Bridge requirements](https://proton.me/support/bridge-for-linux) and [research findings](docs/proton-protocol.md) explain the boundary.

## Installation

Prerequisites: Linux Docker Engine with Compose v2, Git, OpenSSL, internet access for the source/image build, and a Bridge-eligible Proton Mail account. Docker Desktop may work but has not been validated. Allow several GB of disk and build RAM; the complete upstream source is included in the image for redistribution compliance.

```sh
git clone https://github.com/just-a-dev20/protonmail-imap-gateway.git
cd protonmail-imap-gateway
sh scripts/init-secrets.sh
docker compose build
docker compose run --rm gateway setup
docker compose up -d
docker compose ps
docker compose exec gateway python -m gateway healthcheck
```

`init-secrets.sh` generates an independent encryption key, a one-year self-signed localhost TLS certificate, and copies `config.example.toml` to `config.toml`. It refuses to overwrite existing secrets. Trust that certificate explicitly in your client or replace it with a certificate issued by a trusted CA. Never disable certificate validation. Store the master key separately from data-volume backups. Losing it loses access to the stored session; the account can be configured again from scratch.

Linux bind-mounted Compose secrets retain host permissions. The script uses a private mode-0700 `secrets/` directory and readable files so UID 10001 can access mounted secrets. Keep that directory private; files moved outside it need protected permissions. On Windows/WSL, also enforce Windows ACLs or keep secrets on the Linux filesystem. Do not commit or bake secrets into images.

### Interactive setup

The setup command holds an exclusive volume lock and opens the upstream Bridge CLI. Enter:

1. `login`, then answer the Proton username/password prompts. Complete TOTP/2FA and any additional mailbox-password prompt. If human verification appears, open its URL and follow Proton's instructions. No challenge is bypassed.
2. `info` (select the account if prompted). Record the **Bridge-generated** username and password for both mail services. Do not use your Proton password in an email client.
3. `cert export`, then enter `/data/bridge-cert`. The gateway retains the exported public certificate and removes the exported private key when setup finishes.
4. `exit`.

This build defaults both backend listeners to SSL, ports 1143 and 1025, and disables binary autoupdates. Do not toggle `change imap-security` or `change smtp-security` unless repairing an imported configuration. An existing STARTTLS configuration needs each relevant setting toggled to SSL. If you change backend ports using the CLI, also update `backend_port` in `config.toml`.

Do not record setup terminal output: `info` intentionally displays mail credentials and human verification may display a sensitive URL. To reauthenticate: `docker compose stop`, run setup again, then `docker compose up -d`. Never run two Bridge processes against the same volume.

### Client settings

| Setting | IMAP | Outgoing SMTP submission |
|---|---|---|
| Host (on the Docker host) | localhost | localhost |
| Default published port | 1993 | 1465 |
| Connection security | SSL/TLS (implicit) | SSL/TLS (implicit) |
| Authentication | Normal password | Normal password; required |
| Username/password | From Bridge `info` | Same Bridge credentials |

* **Thunderbird:** Add an existing mail account, choose manual configuration, enter the values above and trust the configured certificate. Allow folders to finish synchronizing.
* **Apple Mail:** Add Other Mail Account and enter the same incoming/outgoing values. Manual port settings may be needed; trust the certificate in Keychain.
* **Outlook:** Use a version that supports manually configured IMAP accounts, Advanced setup → IMAP, and require SMTP authentication. Some newer/cloud-connected Outlook variants cannot access localhost or private LAN services; compatibility is unverified. Do not expose the gateway publicly to work around this.
* **Thunderbird Android / K-9 / FairEmail:** Configure a manual IMAP account with SSL/TLS for both services. A phone cannot reach your server via `localhost`; use the explicit LAN/VPN setup below and a trusted server-name certificate. Battery/background sync behavior is client-specific.

**Clients tested:** automated Python TLS/socket clients only; no Thunderbird, Apple Mail, Outlook or Android application tested yet.

## TLS, ports and LAN access

External STARTTLS/plaintext listeners are intentionally omitted. Ports are configurable: `IMAPS_PORT=2993 SMTPS_PORT=2465 docker compose up -d` changes host ports. If you change internal `port` values in `config.toml`, update the container side of Compose's port mappings as well. `backend_port` must match Bridge's stored settings. TLS paths, login/session deadlines, connection budgets and the loopback health port are in `config.toml`. Proton credentials never belong in that file.

Compose publishes only on **127.0.0.1**. Its `GATEWAY_LISTEN=0.0.0.0` and `GATEWAY_ALLOW_LAN=true` enable Docker NAT inside the container; these do not change the host bindings. Containers sharing its network can reach the listeners and must still authenticate.

For LAN/VPN use, replace `127.0.0.1` in each Compose port binding with the intended host interface IP, issue a TLS certificate for a DNS name resolving to that IP, replace the TLS secret files, and recreate the container. Restrict access with a firewall. Keep management/health private. Direct TLS is recommended; any proxy terminating TLS sees credentials and mail. Renew certificates before expiry and recreate the container to reload them.

## Security and operations

Read [the threat model](docs/security.md) before deployment. The server is a decryption endpoint and must be trusted. A compromised Docker host or process memory defeats confidentiality. Local client mail caches need their own protection.

* Separate master-key Docker secret; AES-256-GCM keychain and upstream encrypted vault/cache. Metadata is not all encrypted.
* Non-root UID 10001, read-only root, no Linux capabilities, no-new-privileges, bounded memory/PIDs, disabled core dumps.
* 20 connections/minute globally, one login attempt/connection, 60-second login deadline, one-hour connection lifetime. Clients reconnect after expiry. These are connection controls, not Proton session revocation.
* Gateway JSON logs contain fixed events only. Set `GATEWAY_LOG_LEVEL` in the Compose environment to `debug`, `info` (default), `warning`, or `error` to filter gateway events; this never enables upstream diagnostics. Upstream logging is suppressed because some upstream paths log verification tokens. `docker compose logs` provides lifecycle information, not mailbox diagnostics.
* `GET http://127.0.0.1:8080/healthz` exists **inside the container only**. HTTP 200 means both backend TLS greetings succeed; it does not mean logged in, synchronized, or able to send mail. Session/sync fields explicitly say `unknown`.

Back up the `gateway-data` volume while stopped, and keep its master key in a separate protected backup. Revoke Proton sessions through Proton account security settings if compromised. Rebuild to update Bridge/base images; test upgrades before replacing a working deployment. There is no automatic binary replacement.

## Troubleshooting

| Symptom | Check |
|---|---|
| Generic startup failure | Secret files readable by UID 10001, valid 64-hex master key, valid TOML, TLS files present, no concurrent setup process |
| Unhealthy container | Run setup and `cert export`; both backend modes must be SSL; check matching backend ports |
| Certificate error | Client hostname matches SAN, certificate trusted and unexpired; re-export backend cert if Bridge state was recreated |
| Login rejected | Use Bridge `info` credentials; confirm Mail plan eligibility and account connection via setup |
| Immediate disconnects | Global rate limit or one-attempt-per-connection rule; reduce client parallel connections and wait one minute |
| Disconnect after an hour | Expected session expiration; client reconnects, or adjust `session_seconds` |
| Mobile cannot connect | Use the server's LAN/VPN hostname, explicit host port bindings and matching certificate |
| Slow first synchronization | Upstream initial sync may take time; health is not sync progress; inspect CLI account state |
| Wrong encryption key | Restore the matching secret. Do not overwrite the encrypted volume or rotate by replacing the file |

## Development and verification

```sh
python3 -m unittest discover -v
python3 -m pip install ruff==0.16.9
ruff check .
ruff format --check .
sh scripts/test-keychain.sh  # Go 1.26.7 required
docker build --target test -t gateway-test .
docker run --rm --read-only --cap-drop ALL --tmpfs /tmp gateway-test
```

CI runs tests, formatting/lint checks, the encrypted-keychain tests, a Docker build, hardened-container tests, Compose smoke checks and Trivy scans for fixable high/critical vulnerabilities. Dependency versions come from the pinned upstream go.mod/go.sum. See [CONTRIBUTING](CONTRIBUTING.md) for test scope and [validation](docs/validation.md) for actual execution results.

## Limitations and licensing

No Free gateway support, live-account verification, graphical-client certification, optional web UI, sync counters, automatic TLS renewal or automated key rotation. Hardware FIDO2 devices are not mapped into the container; use an upstream-supported authentication method that works in your environment. Outlook/cloud-client accessibility and SMTPUTF8 are not guaranteed. Transport tests do not test Proton PGP correctness; this is inherited from upstream and requires its own integration testing.

See [Bridge comparison](docs/bridge-comparison.md), [protocol/licensing research](docs/proton-protocol.md), [LICENSE](LICENSE) and [security reporting](SECURITY.md). The Docker image includes the exact modified Bridge source and vendored dependencies at `/usr/share/gateway/bridge-corresponding-source.tar.gz`. Preserve corresponding-source availability and all notices when distributing binaries. This project is not affiliated with Proton AG.
