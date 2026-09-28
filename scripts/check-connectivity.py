"""Check the real published TLS endpoints without accessing an account or mail."""

import imaplib
import os
import smtplib
import ssl

context = ssl.create_default_context(cafile="secrets/tls_cert.pem")
with imaplib.IMAP4_SSL(
    "localhost", int(os.environ.get("IMAPS_PORT", "1993")), ssl_context=context, timeout=10
) as client:
    status, _ = client.noop()
    if status != "OK":
        raise RuntimeError("IMAP NOOP failed")
with smtplib.SMTP_SSL(
    "localhost", int(os.environ.get("SMTPS_PORT", "1465")), context=context, timeout=10
) as client:
    if client.ehlo()[0] != 250 or client.noop()[0] != 250:
        raise RuntimeError("SMTP EHLO/NOOP failed")
print("Published IMAPS and SMTP TLS connectivity verified; account state remains untested.")
