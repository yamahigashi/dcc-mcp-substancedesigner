"""Command-line entry point for dcc-mcp-substancedesigner."""

from __future__ import annotations

import argparse
import http.client
import logging
import os
import socket
import subprocess
import sys
import time
from typing import Optional

from dcc_mcp_substancedesigner import DEFAULT_MCP_PORT, DEFAULT_SD_BRIDGE_PORT, start_server, stop_server
from dcc_mcp_substancedesigner.bridge import SubstanceDesignerBridgeClient, SubstanceDesignerBridgeError
from dcc_mcp_substancedesigner.server import DEFAULT_GATEWAY_PORT

MIN_SUBSTANCE_DESIGNER_VERSION = (16, 0)


def main(argv: Optional[list[str]] = None) -> int:
    """Run the Substance Designer MCP server."""
    parser = argparse.ArgumentParser(description="Substance Designer MCP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_MCP_PORT, help="MCP port to listen on")
    parser.add_argument("--sd-host", default="127.0.0.1", help="Substance Designer bridge host")
    parser.add_argument("--sd-port", type=int, default=DEFAULT_SD_BRIDGE_PORT, help="Substance Designer bridge port")
    parser.add_argument("--gateway-port", type=int, default=None, help="Gateway port")
    parser.add_argument(
        "--check-bridge",
        action="store_true",
        help="Send a diagnostic command to the Substance Designer plugin bridge and exit",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.check_bridge:
        return check_bridge(args.sd_host, args.sd_port)

    gateway_port = _resolve_gateway_port(args.gateway_port)
    try:
        _preflight_gateway_port(gateway_port)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    try:
        server = start_server(port=args.port, sd_host=args.sd_host, sd_port=args.sd_port, gateway_port=gateway_port)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Substance Designer MCP server started: {server.mcp_url}")
    print(f"Substance Designer bridge target: {args.sd_host}:{args.sd_port}")
    print("Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_server()

    return 0


def check_bridge(host: str, port: int) -> int:
    """Check the Substance Designer plugin bridge without starting the MCP server."""
    client = SubstanceDesignerBridgeClient(host=host, port=port)
    try:
        result = client.command("diagnostic")
    except SubstanceDesignerBridgeError as exc:
        print(f"Bridge check failed: {exc}", file=sys.stderr)
        return 1

    if not isinstance(result, dict):
        print("Bridge check failed: diagnostic response must be an object", file=sys.stderr)
        return 1

    if result.get("sd_running") is False:
        print("Bridge check failed: Substance Designer is not running according to diagnostics", file=sys.stderr)
        return 1

    sd_version = result.get("sd_version")
    if not sd_version:
        print("Bridge check failed: diagnostic response did not include sd_version", file=sys.stderr)
        return 1

    print(f"Substance Designer version: {sd_version}")
    if not _version_at_least(str(sd_version), MIN_SUBSTANCE_DESIGNER_VERSION):
        print(
            f"Bridge check failed: Substance 3D Designer 16.0+ is required (reported {sd_version})",
            file=sys.stderr,
        )
        return 1
    print(f"Bridge check succeeded: {host}:{port}")
    return 0


def _resolve_gateway_port(cli_port: int | None) -> int:
    if cli_port is not None:
        return cli_port
    env_port = os.environ.get("DCC_MCP_GATEWAY_PORT", "")
    return int(env_port) if env_port.isdigit() else DEFAULT_GATEWAY_PORT


def _preflight_gateway_port(port: int) -> None:
    if port <= 0:
        return
    if not _tcp_port_is_open("127.0.0.1", port):
        try:
            _assert_tcp_port_can_bind("127.0.0.1", port)
        except OSError as exc:
            raise RuntimeError(_gateway_port_conflict_message(port, f"bind failed: {exc}")) from exc
        return

    connection: http.client.HTTPConnection | None = None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
        connection.request("GET", "/health")
        response = connection.getresponse()
        response.read()
    except OSError as exc:
        raise RuntimeError(_gateway_port_conflict_message(port, str(exc))) from exc
    finally:
        if connection is not None:
            connection.close()

    if response.status != 200:
        raise RuntimeError(_gateway_port_conflict_message(port, f"GET /health returned HTTP {response.status}"))


def _tcp_port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((host, port)) == 0


def _assert_tcp_port_can_bind(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, port))


def _gateway_port_conflict_message(port: int, reason: str) -> str:
    owner = _gateway_port_owner_hint(port)
    owner_text = f"\n{owner}" if owner else ""
    return (
        f"Gateway port 127.0.0.1:{port} is occupied but is not responding as a DCC MCP gateway "
        f"({reason}). Stop the process using that port or restart it before launching this adapter."
        f"{owner_text}\n"
        f"Windows: netstat -ano | findstr :{port}\n"
        f"Windows: Stop-Process -Id <PID>"
    )


def _gateway_port_owner_hint(port: int) -> str:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0:
        return ""

    matches = []
    suffix = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        state = parts[3]
        pid = parts[4]
        if local_address.endswith(suffix) and state.upper() == "LISTENING":
            matches.append(f"Port owner: PID {pid} ({line.strip()})")
    return "\n".join(matches)


def _version_at_least(version: str, minimum: tuple[int, int]) -> bool:
    parts = []
    for token in version.replace("-", ".").split("."):
        if not token.isdigit():
            break
        parts.append(int(token))
    if not parts:
        return False
    major = parts[0]
    minor = parts[1] if len(parts) > 1 else 0
    return (major, minor) >= minimum


if __name__ == "__main__":
    sys.exit(main())
