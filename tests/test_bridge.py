"""Tests for the Substance Designer bridge protocol helpers."""

from __future__ import annotations

import json
import socket
import struct
import threading
from pathlib import Path
from typing import Any, Dict

import pytest

from dcc_mcp_substancedesigner.bridge import (
    MAX_MESSAGE_BYTES,
    SubstanceDesignerBridgeClient,
    SubstanceDesignerBridgeError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_CLIENT_PATH = REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "bridge.py"


def run_fake_bridge(response: Dict[str, Any]) -> tuple[int, Dict[str, Any], threading.Thread]:
    """Run a one-shot fake Substance Designer bridge."""
    captured = {}
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    def handle_once() -> None:
        conn, _addr = server_sock.accept()
        with conn:
            header = conn.recv(4)
            message_length = struct.unpack(">I", header)[0]
            payload = conn.recv(message_length)
            captured["payload"] = json.loads(payload.decode("utf-8"))
            response_bytes = json.dumps(response).encode("utf-8")
            conn.sendall(struct.pack(">I", len(response_bytes)) + response_bytes)
        server_sock.close()

    thread = threading.Thread(target=handle_once)
    thread.start()
    return port, captured, thread


def test_bridge_client_sends_length_prefixed_json() -> None:
    """The bridge client should match the plugin's length-prefixed protocol."""
    port, captured, thread = run_fake_bridge({"status": "ok", "result": {"version": "test"}})

    response = SubstanceDesignerBridgeClient(port=port).send("get_scene_info", {"detail": True})
    thread.join(timeout=2)

    assert captured["payload"] == {"type": "get_scene_info", "params": {"detail": True}}
    assert response == {"status": "ok", "result": {"version": "test"}}


def test_bridge_client_does_not_serialize_independent_connections() -> None:
    """Per-request sockets should not be guarded by one client-wide response lock."""
    source = BRIDGE_CLIENT_PATH.read_text(encoding="utf-8")

    assert "import threading" not in source
    assert "_lock" not in source


def test_bridge_command_unwraps_success_result() -> None:
    port, _captured, thread = run_fake_bridge({"status": "success", "result": {"package_count": 1}})

    response = SubstanceDesignerBridgeClient(port=port).command("get_scene_info")
    thread.join(timeout=2)

    assert response == {"package_count": 1}


def test_bridge_command_raises_plugin_error() -> None:
    port, _captured, thread = run_fake_bridge({"status": "error", "message": "No user packages loaded"})

    with pytest.raises(SubstanceDesignerBridgeError, match="No user packages loaded"):
        SubstanceDesignerBridgeClient(port=port).command("get_scene_info")
    thread.join(timeout=2)


def test_bridge_command_preserves_plugin_error_details() -> None:
    details = {
        "parameter_id": "offset",
        "expected_type": "float2",
        "received_value_type": "dict",
    }
    port, _captured, thread = run_fake_bridge(
        {"status": "error", "message": "Expected float2 mapping with x, y", "details": details}
    )

    with pytest.raises(SubstanceDesignerBridgeError, match="Expected float2") as raised:
        SubstanceDesignerBridgeClient(port=port).command("set_parameter")
    thread.join(timeout=2)

    assert raised.value.details == details


def test_bridge_rejects_invalid_command_before_socket() -> None:
    client = SubstanceDesignerBridgeClient(port=1)

    with pytest.raises(SubstanceDesignerBridgeError, match="command type"):
        client.send("")

    with pytest.raises(SubstanceDesignerBridgeError, match="params"):
        client.send("get_scene_info", [])  # type: ignore[arg-type]


def test_bridge_rejects_oversized_request_before_socket(monkeypatch) -> None:
    client = SubstanceDesignerBridgeClient(port=1)
    monkeypatch.setattr("dcc_mcp_substancedesigner.bridge.MAX_MESSAGE_BYTES", 8)

    with pytest.raises(SubstanceDesignerBridgeError, match="Request too large"):
        client.send("get_scene_info")


def test_bridge_rejects_oversized_response() -> None:
    port, thread = _run_raw_bridge(struct.pack(">I", MAX_MESSAGE_BYTES + 1))

    with pytest.raises(SubstanceDesignerBridgeError, match="Response too large"):
        SubstanceDesignerBridgeClient(port=port).send("get_scene_info")
    thread.join(timeout=2)


def test_bridge_reports_closed_response_payload() -> None:
    port, thread = _run_raw_bridge(struct.pack(">I", 10) + b"{")

    with pytest.raises(SubstanceDesignerBridgeError, match="response payload"):
        SubstanceDesignerBridgeClient(port=port).send("get_scene_info")
    thread.join(timeout=2)


def _run_raw_bridge(response: bytes) -> tuple[int, threading.Thread]:
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    def handle_once() -> None:
        conn, _addr = server_sock.accept()
        with conn:
            header = conn.recv(4)
            message_length = struct.unpack(">I", header)[0]
            conn.recv(message_length)
            conn.sendall(response)
        server_sock.close()

    thread = threading.Thread(target=handle_once)
    thread.start()
    return port, thread
