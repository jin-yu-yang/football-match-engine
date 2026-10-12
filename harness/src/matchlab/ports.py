"""UDP port slots for parallel matches."""

from __future__ import annotations

import socket
import subprocess
import time
from dataclasses import dataclass

BASE_PORT = 16000
STRIDE = 10


class PortInUseError(RuntimeError):
    """A port of the match slot is already in use."""


@dataclass(frozen=True)
class PortSet:
    player: int
    coach: int
    olcoach: int


def port_set(slot: int, base: int = BASE_PORT) -> PortSet:
    first = base + slot * STRIDE
    return PortSet(first, first + 1, first + 2)


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind(("", port))
        except OSError:
            return False
    return True


def ensure_free(ports: PortSet) -> None:
    for port in (ports.player, ports.coach, ports.olcoach):
        if not _free(port):
            raise PortInUseError(f"UDP port {port} is in use. Stop the other server, or use another slot.")


def is_bound(port: int) -> bool:
    """True when some process has a UDP socket on this port (Linux /proc). Does not touch the port."""
    for table in ("/proc/net/udp", "/proc/net/udp6"):
        try:
            with open(table) as fh:
                lines = fh.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            local = line.split()[1]
            if int(local.rsplit(":", 1)[1], 16) == port:
                return True
    return False


def wait_until_bound(port: int, *, timeout_s: float = 10.0, proc: subprocess.Popen | None = None) -> None:
    # Read /proc instead of binding the port: a test bind could make the starting server fail with EADDRINUSE.
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_bound(port):
            return
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"the server exited with code {proc.returncode} before it opened port {port}")
        time.sleep(0.05)
    raise RuntimeError(f"the server did not open port {port} within {timeout_s} s")
