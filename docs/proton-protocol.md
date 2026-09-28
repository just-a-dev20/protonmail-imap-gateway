# Proton protocol and reuse research

Research date: 2026-09-28. These are source/documentation findings, not live-account results.

## Sources inspected

* [Proton Bridge](https://github.com/ProtonMail/proton-bridge/tree/87b5832e4fdaf30638c91a3b19f84c96e3f6a466), pinned revision `87b5832e4fdaf30638c91a3b19f84c96e3f6a466` (3.27.0 development source).
* [Proton WebClients](https://github.com/ProtonMail/WebClients/tree/166034d71798486babaecd180cca09da0457ceb3), revision `166034d71798486babaecd180cca09da0457ceb3`.
* [Go Proton API](https://github.com/ProtonMail/go-proton-api/tree/882710fb04bbe615ba08e8b457e277009292ce49), revision `882710fb04bbe615ba08e8b457e277009292ce49`. Bridge itself uses the version recorded in its pinned go.mod/go.sum, not this research checkout.
* [Official Linux availability](https://proton.me/support/bridge-for-linux), [login requirements](https://proton.me/support/bridge-linux-login-error), and [CLI guide](https://proton.me/support/bridge-cli-guide).

## Authentication and account entitlement

Bridge `internal/bridge/user.go` calls `NewClientWithLoginWithHVToken`, supports `Auth2FA`, and then `LoginUser` with the mailbox key password. The Proton API implementation uses SRP authentication; Bridge relies on Proton's Go SRP library, API session identifiers, refresh tokens, and mailbox keys. Session refresh goes through `NewClientWithRefresh`; invalid refresh tokens require login again. Proton passwords are entered interactively rather than passed in environment variables or command arguments.

WebClients `packages/shared/lib/api/auth.ts` defines `core/v4/auth/info`, `core/v4/auth/modulus`, and session operations. Its mail application calls Proton mail APIs and uses client-side cryptography. Free users can use Proton's official web application; this does not establish that a third-party IMAP gateway is entitled to use those interfaces as Bridge.

Go Proton API `response.go` defines **PaidPlanRequired = 10004**. Bridge `internal/frontend/grpc/service_methods.go` handles that API error as a paid-plan requirement. This is evidence of an API entitlement response, **not evidence identifying every server endpoint or the exact timing of enforcement**: server implementation is not public here. No live Free account was tested. Official support documentation explicitly limits Bridge to paid Mail plans. The gateway preserves the upstream app identity and all entitlement handling. It does not spoof the web client, remove checks, or work around CAPTCHA/human verification.

**Decision:** support Bridge-eligible paid accounts only. Free account login/read/send through this gateway remain unsupported. The official web app's Free functionality is not reused to assert or implement gateway support.

## Protocol and encryption implementation

The gateway adds a TLS transport boundary around Bridge. Bridge owns SASL authentication and generates a separate local client password. Its Gluon IMAP backend owns mailbox UIDs, synchronization, folder/label mapping, flags, FETCH/SEARCH/STORE/COPY/MOVE/EXPUNGE/IDLE, drafts, sent, spam and trash. The SMTP implementation sends through Proton's API rather than delivering directly to other domains.

Bridge uses Go Proton API, GopenPGP, go-crypto and go-srp, at the locked versions in `upstream/go.mod` and `upstream/go.sum`. The security overlay updates x/crypto and gRPC plus resolver-selected dependencies; see [the dependency record](../upstream/DEPENDENCIES.md). It unlocks mailbox/address keys and decrypts and encrypts messages and attachments using those maintained implementations. Key changes and recipient-specific encryption are upstream responsibilities. No PGP, SRP, or MIME implementation is duplicated here. The Python transport does not inspect message bodies after authentication.

The backend interface is a pair of authenticated TLS sockets, keeping mail semantics independent of the gateway configuration, lifecycle and access-control code. Protocol support inherits upstream behavior; passing mock transport tests does not establish every command's end-to-end semantics.

## Licenses and changes

The inspected Bridge and WebClients repositories contain GPLv3 licenses. Bridge source headers specify GPL-3.0-or-later. This project's original source is GPL-3.0-or-later. No web-client source is copied. Bridge is built from an exact commit, with a checked-in security dependency overlay and dependency license files retained by `go mod vendor`.

The build copies an openly supplied Linux keychain replacement and patches default TLS modes, disables automatic binary updates, discards Bridge logrus logging, and fails closed on keychain errors instead of using the desktop insecure-vault fallback. No authentication, entitlement, mail protocol, or message-crypto code is changed. Patches are in `scripts/patch_upstream.py` and `upstream/`; the Docker image contains the exact modified source plus vendored dependencies in `/usr/share/gateway/bridge-corresponding-source.tar.gz`. Distributors must retain licenses and make the corresponding source available with any distributed binaries. Base-image/system components retain their own licenses. Proton's names are trademarks; this is an independent project, without implied endorsement.

Review the patches and upstream dependency licenses on every upgrade. A successful build alone is not a license audit or evidence of client compatibility.
