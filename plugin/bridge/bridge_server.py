"""TCP bridge server for the Substance Designer host plugin."""

from __future__ import annotations

import json
import select
import socket
import threading
import time
import traceback
from collections.abc import Callable
from typing import TypeAlias

from ..json_types import JsonMap, JsonScalar, JsonValue
from .bridge_protocol import recv_framed, send_framed
from .bridge_types import CommandDispatcher, JsonFallbackValue, MainThreadRunner

CLIENT_TIMEOUT: int = 130
ACCEPT_BACKLOG: int = 5
DiagnosticValue: TypeAlias = JsonValue | tuple["DiagnosticValue", ...] | JsonFallbackValue


def execute_safe_command(
    command: JsonValue,
    handler: CommandDispatcher,
    run_on_main: MainThreadRunner,
    log: Callable[[str], None],
) -> JsonMap:
    """Validate and execute a decoded command payload without leaking exceptions."""
    try:
        if not isinstance(command, dict):
            return {"status": "error", "message": "Command must be a JSON object"}
        cmd_type = command.get("type")
        params = command.get("params", {})
        if not isinstance(cmd_type, str) or not cmd_type.strip():
            return {"status": "error", "message": "Command type must be a non-empty string"}
        if not isinstance(params, dict):
            return {"status": "error", "message": "Command params must be a JSON object"}
        log("Executing: {}".format(cmd_type))
        result = run_on_main(handler.dispatch, cmd_type, params)
        log("Done: {}".format(cmd_type))
        if result is None:
            raise RuntimeError("Command '{}' returned no result.".format(cmd_type))
        return {"status": "success", "result": result}
    except BaseException as exc:
        command_name = command.get("type", "?") if isinstance(command, dict) else "?"
        log("Error in {}: {}".format(command_name, exc))
        try:
            traceback.print_exc()
        except Exception:
            pass
        response: JsonMap = {"status": "error", "message": str(exc)}
        details = error_details(exc)
        if details:
            response["details"] = details
        return response


def error_details(exc: BaseException) -> JsonMap:
    """Return structured, JSON-safe exception details when available."""
    raw_details = getattr(exc, "details", None)
    if not isinstance(raw_details, dict):
        return {}
    return {str(key): json_safe_detail(value) for key, value in raw_details.items()}


def json_safe_detail(value: DiagnosticValue) -> JsonValue:
    """Return one JSON-safe diagnostic detail value."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [json_safe_detail(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe_detail(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_detail(item) for key, item in value.items()}
    return str(value)


def handle_bridge_client(
    client: socket.socket,
    addr: tuple[str, int],
    port: int,
    timeout: int,
    execute_safe: Callable[[JsonValue], JsonMap],
    json_default: Callable[[JsonFallbackValue], JsonScalar],
    log: Callable[[str], None],
) -> None:
    """Read, execute, and respond to one bridge client command."""
    try:
        client.setblocking(True)
        client.settimeout(timeout)
        log("Client on port {}: {}".format(port, addr))

        payload = recv_framed(client, timeout=timeout)
        if payload is None:
            return

        try:
            command = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            send_framed(
                client,
                json.dumps({"status": "error", "message": "Invalid JSON: {}".format(exc)}).encode("utf-8"),
            )
            return

        response = execute_safe(command)
        send_framed(client, json.dumps(response, default=json_default).encode("utf-8"))

    except socket.timeout:
        log("Timeout from client on port {}".format(port))
    except ConnectionResetError:
        pass
    except Exception as exc:
        log("Error handling client on port {}: {}".format(port, exc))
    finally:
        try:
            client.close()
        except Exception:
            pass


class SDMCPServer:
    """Single-command-per-connection TCP bridge server."""

    def __init__(
        self,
        handler: CommandDispatcher,
        run_on_main: MainThreadRunner,
        json_default: Callable[[JsonFallbackValue], JsonScalar],
        log: Callable[[str], None],
        version: tuple[int, int, int],
        ports: list[int],
    ) -> None:
        """Create a bridge server with injected host callbacks."""
        self.host = "127.0.0.1"
        self.ports = ports
        self.running = False
        self.listeners = {}
        self._thread = None
        self._handler = handler
        self._run_on_main = run_on_main
        self._json_default = json_default
        self._log = log
        self._version = version

    def start(self) -> None:
        """Start listening on all configured bridge ports."""
        self.running = True
        for port in self.ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.host, port))
                sock.listen(ACCEPT_BACKLOG)
                sock.setblocking(False)
                self.listeners[port] = sock
                self._log("Listening on {}:{}".format(self.host, port))
            except Exception as e:
                self._log("Failed to bind port {}: {}".format(port, e))

        if not self.listeners:
            self._log("ERROR: No ports could be opened!")
            return

        self._thread = threading.Thread(target=self._serve_loop, daemon=True, name="SD-MCP-Serve")
        self._thread.start()
        self._log("v{} running on ports: {}".format(".".join(map(str, self._version)), list(self.listeners.keys())))

    def stop(self) -> None:
        """Stop all listeners owned by this bridge server."""
        self.running = False
        for sock in self.listeners.values():
            try:
                sock.close()
            except Exception:
                pass
        self.listeners.clear()
        self._log("Server stopped")

    def _serve_loop(self) -> None:
        """Accept client sockets until the server is stopped."""
        while self.running:
            readable = list(self.listeners.values())
            if not readable:
                time.sleep(0.1)
                continue
            try:
                ready, _, _ = select.select(readable, [], [], 0.1)
            except (OSError, ValueError):
                if not self.running:
                    break
                time.sleep(0.1)
                continue

            for listener in ready:
                port = next((p for p, s in self.listeners.items() if s is listener), None)
                if port is None:
                    continue
                try:
                    client, addr = listener.accept()
                except (BlockingIOError, OSError):
                    continue
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client, addr, port),
                    daemon=True,
                    name="SD-MCP-Client-{}-{}".format(port, addr[1]),
                )
                client_thread.start()

    def _handle_client(self, client: socket.socket, addr: tuple[str, int], port: int) -> None:
        """Read, execute, and respond to one bridge client command."""
        handle_bridge_client(
            client,
            addr,
            port,
            CLIENT_TIMEOUT,
            self._execute_safe,
            self._json_default,
            self._log,
        )

    def _execute_safe(self, command: JsonValue) -> JsonMap:
        """Validate and execute a decoded command payload without leaking exceptions."""
        return execute_safe_command(command, self._handler, self._run_on_main, self._log)
