# Validation record

Initial implementation, 2026-09-28.

* Local Python 3.13: 20 account-free unit and TLS integration tests pass.
* Go 1.26.7: the actual encrypted keychain adapter passes round-trip, fresh-nonce, plaintext-absence, tamper, wrong-key, list and delete tests in an isolated package harness.
* Ruff formatting and linting are run before publication.
* Docker is absent from the authoring environment. Docker/Compose validation is delegated to the repository's actual GitHub Actions run; its result must be checked before describing the image as validated.
* No Proton credentials were supplied. No live login, Free account, paid mail synchronization or delivery was tested. No graphical email client was tested.

The protocol fixture acknowledges mock authentication and echoes post-authentication bytes. Tests verify transport preservation for IMAP operations and MIME data, **not mailbox correctness or SMTP delivery**. The account-free container smoke test checks engine initialization, TLS greetings and health only. First production use requires interactive setup and live account/client acceptance testing.
