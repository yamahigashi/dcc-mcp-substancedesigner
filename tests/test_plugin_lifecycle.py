"""Tests for plugin lifecycle helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import TypeAlias

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SERVER_PATH = REPO_ROOT / "plugin" / "bridge" / "bridge_server.py"
BRIDGE_PROTOCOL_PATH = REPO_ROOT / "plugin" / "bridge" / "bridge_protocol.py"
PLUGIN_LIFECYCLE_PATH = REPO_ROOT / "plugin" / "plugin_lifecycle.py"
PLUGIN_REFRESH_PATH = REPO_ROOT / "plugin" / "plugin_refresh.py"

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonMap: TypeAlias = dict[str, JsonValue]


class FakeHandler:
    """Fake command dispatcher."""

    def dispatch(self, cmd_type: str, params: JsonMap) -> JsonValue:
        """Return a fake dispatch payload."""
        return {"cmd_type": cmd_type, "params": params}


class FakeDetailError(RuntimeError):
    """Fake exception carrying bridge diagnostic details."""

    details = {
        "parameter_id": "offset",
        "expected_type": "float2",
        "received_value_type": "dict",
    }


class FakeFailingHandler:
    """Fake command dispatcher that raises a structured error."""

    def dispatch(self, cmd_type: str, params: JsonMap) -> JsonValue:
        """Raise a fake dispatch error."""
        del cmd_type, params
        raise FakeDetailError("Expected float2 mapping with x, y")


class FakeServer:
    """Fake bridge server."""

    def __init__(self, start_result: bool = True) -> None:
        """Initialize server state."""
        self.start_result = start_result
        self.started = False
        self.stopped = False

    def start(self) -> bool:
        """Record server start."""
        self.started = True
        return self.start_result

    def stop(self) -> None:
        """Record server stop."""
        self.stopped = True


class FakeRefreshHandler:
    """Fake refreshed command handler."""

    def __init__(self) -> None:
        """Initialize fake handler registry."""
        self.HANDLERS = {"diagnostic": lambda: None, "refresh_plugin": lambda: None}


def test_start_plugin_server_logs_status_and_starts_server() -> None:
    """Lifecycle helper creates and starts the bridge server."""
    module = _load_plugin_lifecycle_module()
    logs: list[str] = []
    server = FakeServer()

    result = module.start_plugin_server(
        lambda **kwargs: server,
        FakeHandler(),
        lambda fn, cmd_type, params: fn(cmd_type, params),
        lambda value: str(value),
        logs.append,
        (3, 3, 0),
        [9881],
        "C:/PySide",
        "PySide6",
        True,
        lambda: None,
    )

    assert result is server
    assert server.started is True
    assert logs == [
        "Initializing v3.3.0",
        "PySide path injected: C:/PySide",
        "Qt binding: PySide6",
        "Qt invoker ready (Signal/Slot dispatch)",
        "Plugin v3.3.0 ready! Port: [9881]",
    ]


def test_start_plugin_server_reports_start_failure() -> None:
    """Lifecycle helper logs and reports startup failures."""
    module = _load_plugin_lifecycle_module()
    logs: list[str] = []
    reported: list[bool] = []

    def fail_factory(**kwargs: JsonValue) -> FakeServer:
        """Raise a fake startup failure."""
        raise RuntimeError("boom")

    result = module.start_plugin_server(
        fail_factory,
        FakeHandler(),
        lambda fn, cmd_type, params: fn(cmd_type, params),
        lambda value: str(value),
        logs.append,
        (3, 3, 0),
        [9881],
        None,
        None,
        False,
        lambda: reported.append(True),
    )

    assert result is None
    assert "FATAL: Failed to start server: boom" in logs
    assert reported == [True]


def test_start_plugin_server_does_not_log_ready_when_server_start_returns_false() -> None:
    """Lifecycle helper treats a false start result as not ready."""
    module = _load_plugin_lifecycle_module()
    logs: list[str] = []
    server = FakeServer(start_result=False)

    result = module.start_plugin_server(
        lambda **kwargs: server,
        FakeHandler(),
        lambda fn, cmd_type, params: fn(cmd_type, params),
        lambda value: str(value),
        logs.append,
        (3, 3, 0),
        [9881],
        "C:/PySide",
        "PySide6",
        True,
        lambda: None,
    )

    assert result is None
    assert server.started is True
    assert "Plugin v3.3.0 ready! Port: [9881]" not in logs


def test_stop_plugin_server_stops_when_present() -> None:
    """Lifecycle helper stops an existing server."""
    module = _load_plugin_lifecycle_module()
    logs: list[str] = []
    server = FakeServer()

    module.stop_plugin_server(server, logs.append)

    assert logs == ["Uninitializing"]
    assert server.stopped is True


def test_bridge_server_returns_structured_error_details() -> None:
    """Bridge command execution preserves exception details in error responses."""
    module = _load_bridge_server_module()

    response = module.execute_safe_command(
        {"type": "set_parameter", "params": {}},
        FakeFailingHandler(),
        lambda func, *args: func(*args),
        lambda _message: None,
    )

    assert response == {
        "status": "error",
        "message": "Expected float2 mapping with x, y",
        "details": {
            "parameter_id": "offset",
            "expected_type": "float2",
            "received_value_type": "dict",
        },
    }


def test_bridge_server_start_returns_false_when_no_ports_opened() -> None:
    """Bridge server reports not running when no listener opens."""
    module = _load_bridge_server_module()
    logs: list[str] = []
    server = module.SDMCPServer(
        handler=FakeHandler(),
        run_on_main=lambda fn, cmd_type, params: fn(cmd_type, params),
        json_default=lambda value: str(value),
        log=logs.append,
        version=(3, 3, 0),
        ports=[],
    )

    assert server.start() is False
    assert server.running is False
    assert logs == ["ERROR: No ports could be opened!"]


def test_refresh_plugin_runtime_reloads_plugin_modules_and_replaces_handler() -> None:
    """Refresh helper reloads plugin modules and swaps the bridge handler."""
    module = _load_plugin_refresh_module()
    plugin_module = types.SimpleNamespace(_server=types.SimpleNamespace(_handler=FakeHandler()))
    reloaded: list[str] = []
    modules = {
        "sd_mcp_plugin.bridge": types.ModuleType("sd_mcp_plugin.bridge"),
        "sd_mcp_plugin.commands.command_catalog": types.ModuleType("sd_mcp_plugin.commands.command_catalog"),
        "sd_mcp_plugin.commands.command_handler": types.ModuleType("sd_mcp_plugin.commands.command_handler"),
        "sd_mcp_plugin.bridge.bridge_server": types.ModuleType("sd_mcp_plugin.bridge.bridge_server"),
        "sd_mcp_plugin.python_execution": types.ModuleType("sd_mcp_plugin.python_execution"),
        "sd_mcp_plugin.python_execution.execution": types.ModuleType("sd_mcp_plugin.python_execution.execution"),
        "sd_mcp_plugin.plugin_refresh": types.ModuleType("sd_mcp_plugin.plugin_refresh"),
    }

    result = module.refresh_plugin_runtime(
        plugin_module=plugin_module,
        modules=modules,
        reload_module=lambda loaded_module: reloaded.append(loaded_module.__name__) or loaded_module,
        command_handler_factory=FakeRefreshHandler,
        root_package="sd_mcp_plugin",
    )

    assert result["status"] == "refreshed"
    assert result["handler_count"] == 2
    assert result["handler_commands"] == ["diagnostic", "refresh_plugin"]
    assert reloaded == [
        "sd_mcp_plugin.commands.command_catalog",
        "sd_mcp_plugin.commands.command_handler",
    ]
    assert isinstance(plugin_module._server._handler, FakeRefreshHandler)


def _load_bridge_server_module() -> types.ModuleType:
    """Load bridge server helpers without writing bytecode."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    _load_module("plugin.bridge.bridge_protocol", BRIDGE_PROTOCOL_PATH)
    module = _load_module("plugin.bridge.bridge_server", BRIDGE_SERVER_PATH)
    for module_name in [
        "plugin",
        "plugin.bridge.bridge_protocol",
        "plugin.bridge.bridge_server",
        "plugin.bridge.bridge_types",
    ]:
        sys.modules.pop(module_name, None)
    return module


def _load_plugin_lifecycle_module() -> types.ModuleType:
    """Load plugin lifecycle helpers without writing bytecode."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    _load_module("plugin.bridge.bridge_protocol", BRIDGE_PROTOCOL_PATH)
    _load_module("plugin.bridge.bridge_server", BRIDGE_SERVER_PATH)
    module = _load_module("plugin.plugin_lifecycle", PLUGIN_LIFECYCLE_PATH)
    for module_name in [
        "plugin",
        "plugin.bridge.bridge_protocol",
        "plugin.bridge.bridge_server",
        "plugin.bridge.bridge_types",
        "plugin.plugin_lifecycle",
        "plugin.plugin_lifecycle_types",
    ]:
        sys.modules.pop(module_name, None)
    return module


def _load_plugin_refresh_module() -> types.ModuleType:
    """Load plugin refresh helpers without writing bytecode."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.plugin_refresh", PLUGIN_REFRESH_PATH)
    for module_name in [
        "plugin",
        "plugin.plugin_refresh",
    ]:
        sys.modules.pop(module_name, None)
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path without writing bytecode."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module
