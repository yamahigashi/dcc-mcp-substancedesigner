"""TCP bridge client for the Substance Designer plugin process."""

from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional

DEFAULT_SD_BRIDGE_PORT = 9881
HEADER_SIZE = 4
MAX_MESSAGE_BYTES = 100 * 1024 * 1024


class SubstanceDesignerBridgeError(RuntimeError):
    """Raised when the Substance Designer bridge cannot complete a request."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        """Create a bridge error with optional structured host details."""
        super().__init__(message)
        self.details = details or {}


@dataclass
class SubstanceDesignerBridgeClient:
    """Length-prefixed JSON client matching the Substance Designer plugin bridge."""

    host: str = "127.0.0.1"
    port: int = DEFAULT_SD_BRIDGE_PORT
    connect_timeout: float = 5.0
    response_timeout: float = 120.0

    def send(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send one command to Substance Designer and return the decoded response."""
        if not isinstance(command_type, str) or not command_type.strip():
            raise SubstanceDesignerBridgeError("Bridge command type must be a non-empty string")
        if params is not None and not isinstance(params, dict):
            raise SubstanceDesignerBridgeError("Bridge command params must be an object")

        payload = json.dumps({"type": command_type, "params": params or {}}).encode("utf-8")
        if len(payload) > MAX_MESSAGE_BYTES:
            raise SubstanceDesignerBridgeError(f"Request too large: {len(payload)} bytes")

        try:
            with socket.create_connection((self.host, self.port), timeout=self.connect_timeout) as sock:
                sock.settimeout(self.response_timeout)
                self._send_framed(sock, payload)
                response = self._recv_framed(sock)
        except OSError as exc:
            raise SubstanceDesignerBridgeError(
                f"Cannot connect to Substance Designer on {self.host}:{self.port}: {exc}"
            ) from exc

        try:
            decoded = json.loads(response.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SubstanceDesignerBridgeError(f"Invalid JSON from Substance Designer: {exc}") from exc

        if not isinstance(decoded, dict):
            raise SubstanceDesignerBridgeError("Substance Designer bridge returned a non-object response")
        return decoded

    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send a command and return the plugin result or raise a bridge error."""
        response = self.send(command_type, params)
        status = response.get("status")
        if status in {"success", "ok"}:
            return response.get("result", {})
        if status == "error":
            details = response.get("details")
            raise SubstanceDesignerBridgeError(
                str(response.get("message", "Unknown Substance Designer error")),
                details=details if isinstance(details, dict) else None,
            )
        return response

    @staticmethod
    def _send_framed(sock: socket.socket, payload: bytes) -> None:
        sock.sendall(struct.pack(">I", len(payload)) + payload)

    @classmethod
    def _recv_framed(cls, sock: socket.socket) -> bytes:
        header = cls._recv_exact(sock, HEADER_SIZE)
        if header is None:
            raise SubstanceDesignerBridgeError("Connection closed while reading response header")
        message_length = struct.unpack(">I", header)[0]
        if message_length > MAX_MESSAGE_BYTES:
            raise SubstanceDesignerBridgeError(f"Response too large: {message_length} bytes")
        if message_length == 0:
            return b""
        payload = cls._recv_exact(sock, message_length)
        if payload is None:
            raise SubstanceDesignerBridgeError("Connection closed while reading response payload")
        return payload

    @staticmethod
    def _recv_exact(sock: socket.socket, byte_count: int) -> Optional[bytes]:
        data = b""
        while len(data) < byte_count:
            chunk = sock.recv(byte_count - len(data))
            if not chunk:
                return None
            data += chunk
        return data
