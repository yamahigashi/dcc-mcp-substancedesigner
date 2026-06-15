"""Substance Designer host plugin entrypoint for dcc-mcp-substancedesigner.

The adapter talks to this plugin over a local TCP bridge using a 4-byte
big-endian length-prefixed JSON protocol. The bridge accepts one command per
connection and dispatches all Substance Designer API calls on the Qt main
thread.

MCP-facing tool policy, validation, and schema normalization live in the Python
adapter package under ``src/dcc_mcp_substancedesigner``. Host-side command
implementation lives in ``plugin.commands.command_handler``.
"""

from __future__ import annotations

from typing import cast

from .bridge.bridge_server import SDMCPServer
from .commands.command_handler import CommandHandler
from .host.host_runtime import PYSIDE_PATH, QT_BINDING_USED, invoker_ready, run_on_main
from .plugin_constants import DEFAULT_PORTS, PLUGIN_VERSION
from .plugin_lifecycle import (
    MainThreadRunner,
    ServerController,
    json_safe,
    log,
    start_plugin_server,
    stop_plugin_server,
)

_server: ServerController | None = None


def initializeSDPlugin() -> None:
    """Initialize the Substance Designer MCP host plugin."""
    global _server
    _server = start_plugin_server(
        SDMCPServer,
        CommandHandler(),
        cast(MainThreadRunner, run_on_main),
        json_safe,
        log,
        PLUGIN_VERSION,
        DEFAULT_PORTS,
        PYSIDE_PATH,
        QT_BINDING_USED,
        invoker_ready(),
        _print_startup_exception,
    )


def uninitializeSDPlugin() -> None:
    """Uninitialize the Substance Designer MCP host plugin."""
    global _server
    stop_plugin_server(_server, log)
    _server = None


def _print_startup_exception() -> None:
    """Print the current startup exception traceback."""
    import traceback

    traceback.print_exc()
