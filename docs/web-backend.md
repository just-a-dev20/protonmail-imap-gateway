# Experimental web-API backend

This mode replaces official Proton Bridge with an independently implemented
Proton API client, [Hydroxide](https://codeberg.org/emersion/hydroxide), pinned at
`80aa6c315cdd378207b6d44d6014240b3a636449`. It does not install or invoke the
paid-plan Bridge engine. It implements authenticated API requests and local
IMAP/SMTP servers rather than copying Proton's website HTML or requiring a
browser to run permanently.

**Proton Free login, reading and sending have not been verified.** This is an
experimental route to account access, not a verified paid-plan bypass. Proton
can reject the application identity, API version, authentication challenge or
account access. Nothing here changes a server-side entitlement. No paid error
is converted into a successful login.

## Run it

If this repository is already configured, keep your existing secrets and skip
`init-secrets.sh`. Do not run both modes on the same published ports.

```sh
sh scripts/init-secrets.sh
docker compose stop
docker compose -f docker-compose.yml -f compose.web.yml build
docker compose -f docker-compose.yml -f compose.web.yml run --rm gateway setup
docker compose -f docker-compose.yml -f compose.web.yml up -d
docker compose -f docker-compose.yml -f compose.web.yml exec gateway python -m gateway healthcheck
```

Setup asks for the Proton username and invokes Hydroxide's hidden password
prompts. TOTP and a separate mailbox password are supported by upstream. Record
the generated **Bridge password** shown after successful login; use it with the
username you supplied for both mail protocols. This is a Hydroxide-generated
client password, unrelated to official Bridge credentials. Do not send account
passwords or session tokens in issues or chat.

No `cert export` command is needed. Both frontend and loopback backend use the
configured TLS secret. Default settings remain localhost:1993 for IMAPS and
localhost:1465 for SMTP over TLS. Trust `secrets/tls_cert.pem` in your client.
For a custom LAN certificate, set `GATEWAY_WEB_TLS_NAME` to a DNS name present
in that certificate. Connections to the backend still go to 127.0.0.1 and
certificate validation remains enabled.

The overlay uses a separate `gateway-web-data` volume. Do not copy an official
Bridge vault into it. To return to the official engine, stop with the web
overlay and start with the base Compose file.

## API compatibility

Hydroxide implements Proton authentication, SRP exchange, token refresh,
mailbox-key unlocking, message fetching and sending against
`https://mail.proton.me/api`. The upstream application's default identity is
`Other`. `GATEWAY_WEB_APP_VERSION` passes an explicit application-version
identifier to Hydroxide when needed for API compatibility. The value is not
discovered automatically and does not grant account permissions. Stale API
versions can stop working independently of this project.

We do not import a browser session, remove 2FA, solve CAPTCHA, or claim that
Proton supports third-party web-API gateways. If human verification or a
hardware-key/SSO flow is required, this mode stops: upstream does not provide
a complete browser challenge flow. Complete account checks in Proton's own
application; repeating automated login attempts is not a remedy.

## Storage and security differences

Hydroxide stores a cached Proton session and **encrypted login/mailbox
passwords** to support reauthentication. The client password supplies one input
to HKDF-SHA256 and the external 32-byte gateway master secret supplies the salt;
the resulting key protects the credential payload with the maintained NaCl
secretbox implementation. Both inputs are required to recover stored
credentials. The encryption format is gateway-specific and cannot be imported
into unmodified Hydroxide. Back up the master secret separately; restoring only
the volume is insufficient. Wrong keys and tampered/truncated ciphertext fail
closed.

Credential writes are serialized, use mode-0600 temporary files, fsync and
atomic rename. Authentication-manager access is serialized. HTTP requests time
out after 30 seconds. Upstream log output is suppressed; runtime stdout/stderr
are discarded. Interactive setup intentionally displays the newly generated
mail-client password and must not be recorded. The standard gateway connection
limits, TLS, non-root UID, read-only root filesystem and core-dump restriction
also apply here.

Hydroxide's local mailbox database and metadata are **not the encrypted Gluon
cache** used by official Bridge. Treat the entire volume as sensitive and use
host disk encryption. Running processes retain tokens, unlocked keys and
passwords in memory. A compromised Docker host can read them. This backend is
casually maintained upstream and has not received an independent audit here.

## Functional limitations

Upstream describes IMAP support as work in progress. In the pinned source,
mailbox create/delete/rename operations and some mailbox checks are unimplemented;
flag, UID and threading handling have documented upstream gaps. It is not
feature-equivalent to Gluon. Do not use it on irreplaceable mail without a
backup. GUI/mobile clients and real-account synchronization/delivery remain
untested. Supported cryptography and recipient behavior are those implemented
by Hydroxide and Proton's service, not guarantees inferred from API access.

Health reports TLS listener readiness, not account access or successful
synchronization. The normal automated suite needs no Proton credentials.
Container tests can verify TLS, IMAP CAPABILITY/NOOP and SMTP EHLO/NOOP without
proving that a Free account can authenticate, read or send.

## Source and licenses

Hydroxide is MIT-licensed; its notice is included in the image. Gateway changes
are GPL-3.0-or-later. The complete pinned, modified source and vendored dependency
licenses are shipped at `/usr/share/gateway/web-corresponding-source.tar.gz`.
`upstream/web/go.mod` and `go.sum` lock the dependency overlay, including
`golang.org/x/crypto v0.55.0`. No website assets or branding are copied.
