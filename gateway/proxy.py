"""TLS transport. The selected backend owns mail semantics, SASL, and cryptography."""

import asyncio
import collections
import contextlib
import json
import os
import ssl
import time

from gateway.backends import kind, trust


def event(name, level="info"):
    # Callers supply fixed strings, never exceptions or protocol data.
    levels = {"debug": 0, "info": 1, "warning": 2, "error": 3}
    threshold = levels.get(os.environ.get("GATEWAY_LOG_LEVEL", "info"), 1)
    if levels[level] < threshold:
        return
    print(json.dumps({"event": name, "level": level}), flush=True)


class Limiter:
    """Global connection budget also bounds distributed attacks; constant memory."""

    def __init__(self, limit):
        self.limit = limit
        self.times = collections.deque()

    def allow(self, now=None):
        now = time.monotonic() if now is None else now
        while self.times and self.times[0] <= now - 60:
            self.times.popleft()
        if len(self.times) >= self.limit:
            return False
        self.times.append(now)
        return True


class AuthState:
    def __init__(self, protocol):
        self.protocol = protocol
        self.authenticated = asyncio.Event()
        self.tags = set()
        self.lines = 0
        self.attempted = False

    def client_line(self, line):
        self.lines += 1
        if self.lines > 64:
            raise ValueError("pre-auth command limit")
        fields = line.split()
        auth = False
        if self.protocol == "imap" and len(fields) >= 2:
            if fields[1].upper() in (b"LOGIN", b"AUTHENTICATE"):
                auth = True
                self.tags.add(fields[0])
        elif self.protocol == "smtp" and fields and fields[0].upper() == b"AUTH":
            auth = True
        if auth:
            if self.attempted:
                raise ValueError("one authentication attempt per connection")
            self.attempted = True

    def server_line(self, line):
        fields = line.split()
        if self.protocol == "smtp":
            if line.startswith(b"235 ") and self.attempted:
                self.authenticated.set()
            return line.startswith((b"535 ", b"534 ", b"530 "))
        if len(fields) >= 2 and fields[0] != b"*":
            if fields[1].upper() in (b"NO", b"BAD"):
                return True
            if fields[0] in self.tags and fields[1].upper() == b"OK":
                self.authenticated.set()
        return False


async def close(writer):
    if writer:
        writer.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), 2)


class Gateway:
    def __init__(self, config):
        self.config = config
        self.limiter = Limiter(config["security"]["connections_per_minute"])
        self.active = 0
        self.servers = []
        self.tasks = set()
        tls = config["tls"]
        self.front_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.front_tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self.front_tls.load_cert_chain(tls["cert_file"], tls["key_file"])
        backend_ca, self.backend_tls_name = trust(config)
        self.back_tls = ssl.create_default_context(cafile=backend_ca)
        if kind() == "web":
            self.back_tls.load_default_certs()
        self.back_tls.minimum_version = ssl.TLSVersion.TLSv1_2

    async def backend(self, protocol):
        return await asyncio.wait_for(
            asyncio.open_connection(
                "127.0.0.1",
                self.config[protocol]["backend_port"],
                ssl=self.back_tls,
                server_hostname=self.backend_tls_name,
                limit=65536,
                ssl_handshake_timeout=5,
            ),
            6,
        )

    async def relay(self, reader, writer, state, from_client):
        while True:
            if state.authenticated.is_set():
                data = await reader.read(65536)
                reject = False
            else:
                data = await reader.readline()
                reject = False
                if from_client:
                    state.client_line(data)
                else:
                    reject = state.server_line(data)
            if not data:
                return
            writer.write(data)
            await writer.drain()
            if reject:
                return

    async def login_deadline(self, state):
        await asyncio.wait_for(state.authenticated.wait(), self.config["security"]["login_seconds"])
        await asyncio.Future()

    async def handle(self, reader, writer, protocol):
        current = asyncio.current_task()
        self.tasks.add(current)
        upstream = None
        jobs = []
        admitted = False
        try:
            if (
                self.active >= self.config["security"]["max_connections"]
                or not self.limiter.allow()
            ):
                event("connection_rejected", "warning")
                return
            self.active += 1
            admitted = True
            upstream_reader, upstream = await self.backend(protocol)
            state = AuthState(protocol)
            jobs = [
                asyncio.create_task(self.relay(reader, upstream, state, True)),
                asyncio.create_task(self.relay(upstream_reader, writer, state, False)),
                asyncio.create_task(self.login_deadline(state)),
            ]
            done, _ = await asyncio.wait(
                jobs,
                timeout=self.config["security"]["session_seconds"],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for job in done:
                job.result()
        except (OSError, ValueError, asyncio.TimeoutError, ssl.SSLError):
            event("connection_closed", "warning")
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            await close(upstream)
            await close(writer)
            if admitted:
                self.active -= 1
            self.tasks.discard(current)

    async def status(self):
        status = {}
        for protocol in ("imap", "smtp"):
            writer = None
            try:
                reader, writer = await self.backend(protocol)
                greeting = await asyncio.wait_for(reader.readline(), 2)
                status[protocol] = greeting.startswith(b"* OK" if protocol == "imap" else b"220")
            except (OSError, ValueError, asyncio.TimeoutError):
                status[protocol] = False
            finally:
                await close(writer)
        return {
            "healthy": all(status.values()),
            "listeners": status,
            "proton_session": "unknown",
            "sync_status": "unknown",
        }

    async def health(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), 2)
            if line != b"GET /healthz HTTP/1.1\r\n":
                writer.write(
                    b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            else:
                data = await self.status()
                body = json.dumps(data).encode()
                status = b"200 OK" if data["healthy"] else b"503 Service Unavailable"
                writer.write(
                    b"HTTP/1.1 "
                    + status
                    + b"\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
            await writer.drain()
        except (OSError, ValueError, asyncio.TimeoutError):
            pass
        finally:
            await close(writer)

    async def start(self):
        for protocol in ("imap", "smtp"):
            cfg = self.config[protocol]
            self.servers.append(
                await asyncio.start_server(
                    lambda r, w, p=protocol: self.handle(r, w, p),
                    cfg["listen"],
                    cfg["port"],
                    ssl=self.front_tls,
                    ssl_handshake_timeout=5,
                    limit=65536,
                    backlog=64,
                )
            )
        self.servers.append(
            await asyncio.start_server(
                self.health, "127.0.0.1", self.config["health"]["port"], limit=4096
            )
        )
        event("listeners_started")

    async def stop(self):
        for server in self.servers:
            server.close()
            await server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
