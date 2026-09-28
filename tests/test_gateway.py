import asyncio
import contextlib
import copy
import io
import json
import os
import socket
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway.config import load
from gateway.proxy import AuthState, Gateway, Limiter, close, event

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ConfigurationTests(unittest.TestCase):
    def test_defaults_are_loopback(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load(ROOT / "config.example.toml")
        self.assertEqual(config["imap"]["listen"], "127.0.0.1")
        self.assertFalse(config["security"]["allow_lan"])

    def test_lan_requires_opt_in(self):
        with patch.dict(os.environ, {"GATEWAY_LISTEN": "0.0.0.0"}, clear=True):
            with self.assertRaises(ValueError):
                load(ROOT / "config.example.toml")

    def test_explicit_container_network(self):
        with patch.dict(
            os.environ, {"GATEWAY_LISTEN": "0.0.0.0", "GATEWAY_ALLOW_LAN": "true"}, clear=True
        ):
            self.assertEqual(load(ROOT / "config.example.toml")["imap"]["listen"], "0.0.0.0")

    def test_bad_config(self):
        original = (ROOT / "config.example.toml").read_text()
        for old, new in [
            ("port = 1993", "port = 25"),
            ("port = 1993", "port = 1465"),
            ("allow_lan = false", 'allow_lan = "false"'),
            ("login_seconds = 60", "login_seconds = 0"),
            ("[health]", "[unrecognized]"),
        ]:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.toml"
                path.write_text(original.replace(old, new))
                with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
                    load(path)

    def test_limiter_bounded_and_recovers(self):
        limiter = Limiter(2)
        self.assertTrue(limiter.allow(0))
        self.assertTrue(limiter.allow(1))
        for _ in range(1000):
            self.assertFalse(limiter.allow(2))
        self.assertEqual(len(limiter.times), 2)
        self.assertTrue(limiter.allow(60))

    def test_fixed_log_schema(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            event("listeners_started")
        self.assertEqual(
            json.loads(output.getvalue()), {"event": "listeners_started", "level": "info"}
        )

    def test_log_level_filter(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"GATEWAY_LOG_LEVEL": "error"}):
            with contextlib.redirect_stdout(output):
                event("listeners_started")
                event("operation_failed", "error")
        self.assertEqual(
            json.loads(output.getvalue()), {"event": "operation_failed", "level": "error"}
        )


class AuthTests(unittest.TestCase):
    def test_imap_auth_needs_matching_tag(self):
        state = AuthState("imap")
        state.client_line(b"a AUTHENTICATE PLAIN\r\n")
        state.server_line(b"b OK capability\r\n")
        self.assertFalse(state.authenticated.is_set())
        state.server_line(b"a OK authenticated\r\n")
        self.assertTrue(state.authenticated.is_set())

    def test_pipeline_attempts_rejected(self):
        for protocol, line in [("imap", b"a LOGIN user bad\r\n"), ("smtp", b"AUTH PLAIN bad\r\n")]:
            state = AuthState(protocol)
            state.client_line(line)
            with self.assertRaises(ValueError):
                state.client_line(line)

    def test_failures_close(self):
        self.assertTrue(AuthState("imap").server_line(b"a NO bad password\r\n"))
        self.assertTrue(AuthState("imap").server_line(b"a BAD malformed\r\n"))
        self.assertTrue(AuthState("smtp").server_line(b"535 Authentication failed\r\n"))

    def test_command_budget(self):
        state = AuthState("imap")
        for _ in range(64):
            state.client_line(b"a CAPABILITY\r\n")
        with self.assertRaises(ValueError):
            state.client_line(b"a CAPABILITY\r\n")


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.cert = str(Path(cls.directory.name) / "cert.pem")
        cls.key = str(Path(cls.directory.name) / "key.pem")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-keyout",
                cls.key,
                "-out",
                cls.cert,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    async def asyncSetUp(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = load(ROOT / "config.example.toml")
        self.config["tls"] = {
            "cert_file": self.cert,
            "key_file": self.key,
            "bridge_ca_file": self.cert,
        }
        self.config["security"]["connections_per_minute"] = 100
        self.backend_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.backend_tls.load_cert_chain(self.cert, self.key)
        self.backends = []
        self.backend_tasks = set()
        self.received = []
        for protocol in ("imap", "smtp"):
            server = await asyncio.start_server(
                lambda r, w, p=protocol: self.fake(r, w, p), "127.0.0.1", 0, ssl=self.backend_tls
            )
            self.backends.append(server)
            self.config[protocol]["backend_port"] = server.sockets[0].getsockname()[1]
            self.config[protocol]["port"] = free_port()
        self.config["health"]["port"] = free_port()
        self.gateway = Gateway(copy.deepcopy(self.config))
        await self.gateway.start()
        self.client_tls = ssl.create_default_context(cafile=self.cert)

    async def asyncTearDown(self):
        await self.gateway.stop()
        for server in self.backends:
            server.close()
            await server.wait_closed()
        for task in list(self.backend_tasks):
            task.cancel()
        await asyncio.gather(*list(self.backend_tasks), return_exceptions=True)

    async def fake(self, reader, writer, protocol):
        task = asyncio.current_task()
        self.backend_tasks.add(task)
        try:
            writer.write(b"* OK mock IMAP\r\n" if protocol == "imap" else b"220 mock SMTP\r\n")
            await writer.drain()
            line = await reader.readline()
            if not line:
                return
            self.received.append(line)
            success = b"good" in line
            if protocol == "imap":
                writer.write(b"a OK authenticated\r\n" if success else b"a NO rejected\r\n")
            else:
                writer.write(b"235 authenticated\r\n" if success else b"535 rejected\r\n")
            await writer.drain()
            while success:
                data = await reader.read(65536)
                if not data:
                    break
                self.received.append(data)
                writer.write(data)
                await writer.drain()
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            await close(writer)
            self.backend_tasks.discard(task)

    async def connect(self, protocol, context=None):
        return await asyncio.open_connection(
            "127.0.0.1",
            self.config[protocol]["port"],
            ssl=context or self.client_tls,
            server_hostname="localhost",
        )

    async def authenticate(self, protocol):
        reader, writer = await self.connect(protocol)
        await reader.readline()
        writer.write(b"a LOGIN user good\r\n" if protocol == "imap" else b"AUTH PLAIN good\r\n")
        await writer.drain()
        self.assertIn(b"authenticated", await reader.readline())
        return reader, writer

    async def test_imap_commands_and_binary_literals_pass_unchanged(self):
        reader, writer = await self.authenticate("imap")
        commands = [
            b'LIST "" "*"',
            b"SELECT INBOX",
            b"STATUS INBOX (MESSAGES)",
            b"FETCH 1 BODY[]",
            b"UID FETCH 1 FLAGS",
            b"SEARCH ALL",
            b"UID SEARCH UNSEEN",
            b"STORE 1 +FLAGS (\\Seen)",
            b"UID STORE 1 +FLAGS (\\Flagged)",
            b"COPY 1 Trash",
            b"UID MOVE 1 Trash",
            b"EXPUNGE",
            b"IDLE",
        ]
        for command in commands:
            data = b"b " + command + b"\r\n"
            writer.write(data)
            await writer.drain()
            self.assertEqual(await reader.readexactly(len(data)), data)
        payload = b"DONE\r\n" + bytes(range(256)) * 1024
        writer.write(payload)
        await writer.drain()
        self.assertEqual(await reader.readexactly(len(payload)), payload)
        await close(writer)

    async def test_smtp_mime_passes_unchanged(self):
        reader, writer = await self.authenticate("smtp")
        mime = (
            "MAIL FROM:<alice@example.com>\r\nRCPT TO:<bob@example.com>\r\nDATA\r\n"
            "To: bob@example.com\r\nCc: c@example.com\r\nReply-To: r@example.com\r\n"
            "In-Reply-To: <id@example.com>\r\nSubject: Grüße\r\n"
            "Content-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\n"
            "Content-Type: text/html; charset=utf-8\r\n\r\n<b>Hello</b>\r\n--x\r\n"
            "Content-Transfer-Encoding: base64\r\n\r\nAAECAw==\r\n--x--\r\n.\r\n"
        ).encode()
        writer.write(mime)
        await writer.drain()
        self.assertEqual(await reader.readexactly(len(mime)), mime)
        await close(writer)

    async def test_auth_failure_disconnects(self):
        for protocol in ("imap", "smtp"):
            reader, writer = await self.connect(protocol)
            await reader.readline()
            writer.write(b"a LOGIN user bad\r\n" if protocol == "imap" else b"AUTH PLAIN bad\r\n")
            await writer.drain()
            self.assertIn(b"rejected", await reader.readline())
            self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
            await close(writer)

    async def test_untrusted_frontend_cert_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            await self.connect("imap", ssl.create_default_context())

    async def test_untrusted_backend_cert_rejected(self):
        self.gateway.back_tls = ssl.create_default_context()
        reader, writer = await self.connect("imap")
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
        await close(writer)

    async def test_login_timeout(self):
        self.gateway.config["security"]["login_seconds"] = 0.05
        reader, writer = await self.connect("imap")
        await reader.readline()
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
        await close(writer)

    async def test_authenticated_session_expires(self):
        self.gateway.config["security"]["session_seconds"] = 0.1
        reader, writer = await self.authenticate("imap")
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
        await close(writer)

    async def test_oversized_pre_auth_line(self):
        reader, writer = await self.connect("imap")
        await reader.readline()
        writer.write(b"x" * 70000 + b"\r\n")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
        await close(writer)

    async def test_health_endpoint_and_backend_failure(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.config["health"]["port"])
        writer.write(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        response = await reader.read()
        self.assertIn(b"200 OK", response)
        self.assertIn(b'"proton_session": "unknown"', response)
        await close(writer)
        self.backends[0].close()
        await self.backends[0].wait_closed()
        self.assertFalse((await self.gateway.status())["healthy"])

    async def test_rate_limit(self):
        self.gateway.limiter = Limiter(1)
        first_reader, first_writer = await self.connect("imap")
        await first_reader.readline()
        reader, writer = await self.connect("imap")
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
        await close(writer)
        await close(first_writer)
