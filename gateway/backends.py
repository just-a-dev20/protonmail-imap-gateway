"""Select a mail engine without exposing API sessions to mail clients."""

import os
import re
import subprocess


def kind():
    value = os.environ.get("GATEWAY_BACKEND", "bridge")
    if value not in ("bridge", "web"):
        raise ValueError("unknown backend")
    return value


def web_version():
    value = os.environ.get("GATEWAY_WEB_APP_VERSION", "Other")
    if not re.fullmatch(r"[A-Za-z0-9@._+\-]{1,128}", value):
        raise ValueError("invalid API application version")
    return value


def command(config):
    if kind() == "bridge":
        return ["/usr/local/bin/proton-bridge", "--noninteractive"]
    return [
        "/usr/local/bin/hydroxide",
        "-app-version",
        web_version(),
        "-imap-host",
        "127.0.0.1",
        "-smtp-host",
        "127.0.0.1",
        "-imap-port",
        str(config["imap"]["backend_port"]),
        "-smtp-port",
        str(config["smtp"]["backend_port"]),
        "-disable-carddav",
        "-tls-cert",
        config["tls"]["cert_file"],
        "-tls-key",
        config["tls"]["key_file"],
        "serve",
    ]


def trust(config):
    if kind() == "bridge":
        return config["tls"]["bridge_ca_file"], "127.0.0.1"
    name = os.environ.get("GATEWAY_WEB_TLS_NAME", "localhost")
    if not name or len(name) > 253 or any(c.isspace() for c in name):
        raise ValueError("invalid backend TLS name")
    return config["tls"]["cert_file"], name


def setup_web(root):
    print(
        "Experimental Proton web-API backend; Free-account access is unverified.\n"
        "Enter your own Proton credentials at the hidden prompts. TOTP is supported;\n"
        "CAPTCHA/human-verification and hardware-key flows are not automated.\n"
        "Save the generated Bridge password for both mail clients. No cert export is needed."
    )
    username = input("Proton username: ").strip()
    if (
        not username
        or username.startswith("-")
        or len(username) > 254
        or any(c.isspace() for c in username)
    ):
        raise ValueError("invalid username")
    result = subprocess.call(
        [
            "/usr/local/bin/hydroxide",
            "-app-version",
            web_version(),
            "auth",
            username,
        ]
    )
    if result or not (root / "config/hydroxide/auth.json").is_file():
        raise RuntimeError("web API login failed")
