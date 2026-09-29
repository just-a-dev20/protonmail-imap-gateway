import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import backends
from gateway.config import load

ROOT = Path(__file__).resolve().parents[1]


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = load(ROOT / "config.example.toml")

    def test_bridge_default(self):
        self.assertEqual(
            backends.command(self.config), ["/usr/local/bin/proton-bridge", "--noninteractive"]
        )
        self.assertEqual(backends.trust(self.config)[1], "127.0.0.1")

    def test_web_command_has_tls_and_private_backends(self):
        os.environ["GATEWAY_BACKEND"] = "web"
        command = backends.command(self.config)
        self.assertEqual(command[0], "/usr/local/bin/hydroxide")
        self.assertEqual(command[command.index("-imap-host") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("-smtp-host") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("-tls-key") + 1], self.config["tls"]["key_file"])
        self.assertIn("-disable-carddav", command)
        self.assertNotIn("-debug", command)
        self.assertEqual(
            backends.trust(self.config), (self.config["tls"]["cert_file"], "localhost")
        )

    def test_unknown_backend_fails_closed(self):
        os.environ["GATEWAY_BACKEND"] = "typo"
        with self.assertRaises(ValueError):
            load(ROOT / "config.example.toml")

    def test_web_version_validated(self):
        os.environ["GATEWAY_BACKEND"] = "web"
        for value in ("", "a\nb", "-debug true", "x" * 129):
            os.environ["GATEWAY_WEB_APP_VERSION"] = value
            with self.assertRaises(ValueError):
                backends.command(self.config)

    def test_web_setup_does_not_take_password_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config/hydroxide").mkdir(parents=True)
            (root / "config/hydroxide/auth.json").write_text("{}")
            with (
                patch("builtins.input", return_value="alice"),
                patch("builtins.print"),
                patch("gateway.backends.subprocess.call", return_value=0) as call,
            ):
                backends.setup_web(root)
            self.assertEqual(
                call.call_args.args[0],
                ["/usr/local/bin/hydroxide", "-app-version", "Other", "auth", "alice"],
            )

    def test_web_setup_failure_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("builtins.input", return_value="alice"),
                patch("builtins.print"),
                patch("gateway.backends.subprocess.call", return_value=1),
                self.assertRaises(RuntimeError),
            ):
                backends.setup_web(Path(directory))
