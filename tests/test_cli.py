"""Tests for the command-line interface."""

from __future__ import annotations

import json
import socket
import struct
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dcc_mcp_substancedesigner.cli import _preflight_gateway_port, _resolve_gateway_port, _version_at_least, main


def test_cli_check_bridge_success(capsys) -> None:
    port = _run_fake_bridge({"status": "success", "result": {"sd_version": "16.0.0"}})

    exit_code = main(["--check-bridge", "--sd-port", str(port)])

    output = capsys.readouterr()
    assert exit_code == 0
    assert "Bridge check succeeded" in output.out
    assert "16.0.0" in output.out


def test_cli_check_bridge_failure(capsys) -> None:
    exit_code = main(["--check-bridge", "--sd-port", "1"])

    output = capsys.readouterr()
    assert exit_code == 1
    assert "Bridge check failed" in output.err


def test_cli_check_bridge_rejects_unsupported_substance_designer_version(capsys) -> None:
    port = _run_fake_bridge({"status": "success", "result": {"sd_version": "15.0.3"}})

    exit_code = main(["--check-bridge", "--sd-port", str(port)])

    output = capsys.readouterr()
    assert exit_code == 1
    assert "Substance Designer version: 15.0.3" in output.out
    assert "Bridge check succeeded" not in output.out
    assert "Substance 3D Designer 16.0+ is required" in output.err


def test_cli_check_bridge_rejects_missing_diagnostic_version(capsys) -> None:
    port = _run_fake_bridge({"status": "success", "result": {"sd_running": True}})

    exit_code = main(["--check-bridge", "--sd-port", str(port)])

    output = capsys.readouterr()
    assert exit_code == 1
    assert "did not include sd_version" in output.err


def test_cli_check_bridge_rejects_not_running_diagnostic(capsys) -> None:
    port = _run_fake_bridge({"status": "success", "result": {"sd_running": False, "sd_version": "16.0.0"}})

    exit_code = main(["--check-bridge", "--sd-port", str(port)])

    output = capsys.readouterr()
    assert exit_code == 1
    assert "Substance Designer is not running" in output.err


def test_version_at_least_parses_substance_designer_versions() -> None:
    assert _version_at_least("16.0.0", (16, 0)) is True
    assert _version_at_least("16.1.2", (16, 0)) is True
    assert _version_at_least("15.9.9", (16, 0)) is False
    assert _version_at_least("unknown", (16, 0)) is False


def test_gateway_port_resolves_to_adapter_default(monkeypatch) -> None:
    monkeypatch.delenv("DCC_MCP_GATEWAY_PORT", raising=False)

    assert _resolve_gateway_port(None) == 9765


def test_gateway_port_resolves_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DCC_MCP_GATEWAY_PORT", "19765")

    assert _resolve_gateway_port(None) == 19765


def test_gateway_port_cli_override_allows_disable(monkeypatch) -> None:
    monkeypatch.setenv("DCC_MCP_GATEWAY_PORT", "19765")

    assert _resolve_gateway_port(0) == 0


def test_gateway_preflight_allows_free_port() -> None:
    port = _free_tcp_port()

    _preflight_gateway_port(port)


def test_gateway_preflight_rejects_bound_but_closed_port() -> None:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    port = holder.getsockname()[1]

    try:
        with pytest.raises(RuntimeError, match="bind failed"):
            _preflight_gateway_port(port)
    finally:
        holder.close()


def test_gateway_preflight_allows_healthy_gateway() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthyGatewayHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _preflight_gateway_port(port)
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_preflight_rejects_non_http_port_owner() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]

    stop = threading.Event()

    def accept_once() -> None:
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        with conn:
            stop.wait(2)

    thread = threading.Thread(target=accept_once, daemon=True)
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="not responding as a DCC MCP gateway"):
            _preflight_gateway_port(port)
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=1)


def test_console_script_check_bridge_success() -> None:
    port = _run_fake_bridge({"status": "success", "result": {"sd_version": "16.1.0"}})

    result = subprocess.run(
        ["dcc-mcp-substancedesigner", "--check-bridge", "--sd-port", str(port)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Bridge check succeeded" in result.stdout
    assert "16.1.0" in result.stdout


class _HealthyGatewayHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_fake_bridge(response: dict) -> int:
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
            response_bytes = json.dumps(response).encode("utf-8")
            conn.sendall(struct.pack(">I", len(response_bytes)) + response_bytes)
        server_sock.close()

    threading.Thread(target=handle_once, daemon=True).start()
    return port
