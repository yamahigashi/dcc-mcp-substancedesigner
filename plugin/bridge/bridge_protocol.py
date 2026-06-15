"""Length-prefixed TCP framing helpers for the Substance Designer bridge."""

from __future__ import annotations

import socket
import struct

HEADER_SIZE: int = 4
MAX_MSG_SIZE: int = 100 * 1024 * 1024
DEFAULT_COMMAND_TIMEOUT: int = 120

HTTP_REQUEST_PREFIXES: tuple[bytes, ...] = (b"GET ", b"POST", b"HEAD", b"PUT ", b"PATC", b"DELE", b"OPTI")


def recv_framed(sock: socket.socket, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> bytes | None:
    """Receive one length-prefixed payload from a socket."""
    header = recv_exact(sock, HEADER_SIZE, timeout)
    if not header:
        return None
    if looks_like_http_request(header):
        raise ValueError(
            "Received an HTTP request on the raw Substance Designer MCP bridge. "
            "Use dcc-mcp-substancedesigner --check-bridge or the MCP server, not a browser/HTTP client."
        )
    msg_len = struct.unpack(">I", header)[0]
    if msg_len == 0:
        return None
    if msg_len > MAX_MSG_SIZE:
        raise ValueError("Message too large: {} bytes".format(msg_len))
    payload = recv_exact(sock, msg_len, timeout)
    if not payload:
        return None
    return payload


def send_framed(sock: socket.socket, data: bytes) -> None:
    """Send one length-prefixed payload to a socket."""
    if len(data) > MAX_MSG_SIZE:
        raise ValueError("Message too large: {} bytes".format(len(data)))
    sock.sendall(struct.pack(">I", len(data)) + data)


def recv_exact(sock: socket.socket, n: int, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> bytes | None:
    """Read exactly ``n`` bytes from a socket or return None if it closes."""
    sock.settimeout(timeout)
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except socket.timeout as exc:
            raise socket.timeout("Timed out reading {} bytes (got {})".format(n, len(buf))) from exc
        if not chunk:
            return None
        buf += chunk
    return buf


def looks_like_http_request(header: bytes) -> bool:
    """Return whether a 4-byte bridge header looks like an HTTP method prefix."""
    return header in HTTP_REQUEST_PREFIXES
