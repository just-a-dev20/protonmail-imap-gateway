"""Strict configuration. Credentials are deliberately not configurable here."""

import ipaddress
import os
import tomllib
from pathlib import Path

from gateway.backends import kind, web_version


def load(path=None):
    if kind() == "web":
        web_version()
    if os.environ.get("GATEWAY_LOG_LEVEL", "info") not in ("debug", "info", "warning", "error"):
        raise ValueError("invalid log level")
    path = path or os.environ.get("GATEWAY_CONFIG", "/app/config.toml")
    with open(path, "rb") as stream:
        config = tomllib.load(stream)
    allowed = {
        "imap": {"listen", "port", "backend_port"},
        "smtp": {"listen", "port", "backend_port"},
        "tls": {"cert_file", "key_file", "bridge_ca_file"},
        "security": {
            "allow_lan",
            "connections_per_minute",
            "max_connections",
            "session_seconds",
            "login_seconds",
        },
        "health": {"port"},
    }
    if set(config) != set(allowed):
        raise ValueError("invalid configuration sections")
    for section, keys in allowed.items():
        if set(config[section]) != keys:
            raise ValueError("invalid configuration keys")
    security = config["security"]
    if type(security["allow_lan"]) is not bool:
        raise ValueError("allow_lan must be boolean")
    for name in ("connections_per_minute", "max_connections", "session_seconds", "login_seconds"):
        if type(security[name]) is not int or not 1 <= security[name] <= 86400:
            raise ValueError("invalid security limit")
    if os.environ.get("GATEWAY_ALLOW_LAN") == "true":
        security["allow_lan"] = True
    ports = [config["health"]["port"]]
    for protocol in ("imap", "smtp"):
        cfg = config[protocol]
        cfg["listen"] = os.environ.get("GATEWAY_LISTEN", cfg["listen"])
        addr = ipaddress.ip_address(cfg["listen"])
        if not addr.is_loopback and not security["allow_lan"]:
            raise ValueError("non-loopback listener requires allow_lan")
        ports.extend((cfg["port"], cfg["backend_port"]))
    if any(type(p) is not int or not 1024 <= p <= 65535 for p in ports) or len(set(ports)) != len(
        ports
    ):
        raise ValueError("ports must be distinct unprivileged TCP ports")
    for path in config["tls"].values():
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("TLS paths must be absolute")
    return config
