# Validation record

Experimental web backend, 2026-09-29:

* Local Python: 29 unit/TLS integration tests pass, including web backend selection, setup failure, separate certificate trust and hostname rejection.
* The pinned, patched Hydroxide builds with Go 1.26.7 and passes its package suite plus credential-encryption, concurrent-write and API-rejection regression tests.
* The compiled Hydroxide binary was run behind the actual gateway on temporary loopback ports. Verified TLS, IMAP CAPABILITY/NOOP and SMTP EHLO/NOOP passed without a Proton account.
* CI includes a separate web image build, Go race tests for the credential package, hardened-container tests, Compose smoke test and vulnerability scan. Consult the revision's CI run for completion status.
* Free-account login, synchronization, delivery and browser challenge flows remain unverified. No account credentials were used or supplied.

Initial implementation, 2026-09-28.

* Local Python 3.13: 21 account-free unit and TLS integration tests pass.
* Go 1.26.7: the actual encrypted keychain adapter passes round-trip, fresh-nonce, plaintext-absence, tamper, wrong-key, list and delete tests in an isolated package harness.
* Ruff formatting and linting are run before publication.
* Docker is absent from the authoring environment. GitHub Actions has built the actual image, run the transport tests inside the hardened container, initialized Bridge without an account, exported its certificate, started Compose and obtained a successful healthcheck. Both Python 3.11 and 3.13 pass the unit/integration suite. See the [CI runs](https://github.com/just-a-dev20/protonmail-imap-gateway/actions/workflows/ci.yml) for exact revision results.
* The image scanner found vulnerable upstream Go dependencies and unnecessary Python packaging components. The dependency overlay and minimal Debian Python runtime address those findings; scanning continues to fail CI on fixable HIGH/CRITICAL findings. No vulnerability suppressions were added.
* The final smoke test also exercises host-published TLS ports using Python imaplib/smtplib and rejects a wrong master key without creating an insecure vault. Check the latest CI result for those checks.
* No Proton credentials were supplied. No live login, Free account, paid mail synchronization or delivery was tested. No graphical email client was tested.

The protocol fixture acknowledges mock authentication and echoes post-authentication bytes. Tests verify transport preservation for IMAP operations and MIME data, **not mailbox correctness or SMTP delivery**. The account-free container smoke test checks engine initialization, TLS greetings and health only. First production use requires interactive setup and live account/client acceptance testing.
