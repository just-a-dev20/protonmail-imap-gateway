"""Interactive upstream setup and supervised non-root service."""

import asyncio
import contextlib
import fcntl
import os
import resource
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path

from gateway.config import load
from gateway.proxy import Gateway, event


def prepare():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(os.environ.get("GATEWAY_DATA", "/data"))
    for name in ("home", "config", "cache", "share", "keychain", "bridge-cert"):
        (root / name).mkdir(mode=0o700, parents=True, exist_ok=True)
    # Hold for the lifetime of this process, including the interactive child.
    lock = (root / "gateway.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ.update(
        HOME=str(root / "home"),
        XDG_CONFIG_HOME=str(root / "config"),
        XDG_CACHE_HOME=str(root / "cache"),
        XDG_DATA_HOME=str(root / "share"),
        GATEWAY_KEYCHAIN_DIR=str(root / "keychain"),
    )
    key = Path(os.environ.get("GATEWAY_MASTER_KEY_FILE", "/run/secrets/master_key"))
    if len(bytes.fromhex(key.read_text().strip())) != 32:
        raise ValueError("invalid master key")
    os.environ["GATEWAY_MASTER_KEY_FILE"] = str(key)
    return lock, root


async def serve(config):
    gateway = Gateway(config)
    process = await asyncio.create_subprocess_exec(
        "/usr/local/bin/proton-bridge",
        "--noninteractive",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(lambda _loop, _context: event("transport_error", "warning"))
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    jobs = []
    try:
        await gateway.start()
        jobs = [asyncio.create_task(stop.wait()), asyncio.create_task(process.wait())]
        done, _ = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
        if jobs[1] in done:
            raise RuntimeError("bridge stopped")
    finally:
        await gateway.stop()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command == "healthcheck":
        config = load()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{config['health']['port']}/healthz", timeout=20
        ) as response:
            if response.status != 200:
                raise RuntimeError("unhealthy")
        return
    if command not in ("setup", "serve"):
        raise ValueError("use setup, serve, or healthcheck")
    lock, root = prepare()
    with lock:
        if command == "setup":
            print(
                "Use: login (Proton password, 2FA and mailbox password are prompted by Bridge).\n"
                "Then: info (record the separate Bridge client password).\n"
                "Both backend listeners default to SSL in this build. Do not toggle their security mode.\n"
                "Run: cert export, and enter " + str(root / "bridge-cert") + "\n"
                "Run: updates autoupdates disable. Finish with: exit.\n"
                "Keep backend ports 1143/1025 unless you also change config.toml.\n"
                "Human verification must be completed in your browser when prompted.",
                flush=True,
            )
            try:
                result = subprocess.call(["/usr/local/bin/proton-bridge", "--cli"])
            finally:
                # The exported backend private key is not needed by the proxy.
                with contextlib.suppress(FileNotFoundError):
                    (root / "bridge-cert/key.pem").unlink()
            if result:
                raise RuntimeError("setup failed")
            if not (root / "bridge-cert/cert.pem").exists():
                raise RuntimeError("Bridge certificate was not exported")
        else:
            asyncio.run(serve(load()))


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        event("operation_failed_check_setup_and_configuration", "error")
        sys.exit(1)
