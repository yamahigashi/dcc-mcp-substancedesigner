"""Substance Designer MCP server composition boundary."""

from __future__ import annotations

import os
import socket
import sys
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from dcc_mcp_substancedesigner.__version__ import __version__
from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    SubstanceAuthoringReferenceProducer,
)
from dcc_mcp_substancedesigner.bridge import DEFAULT_SD_BRIDGE_PORT, SubstanceDesignerBridgeClient
from dcc_mcp_substancedesigner.commands import ENV_SD_BRIDGE_HOST, ENV_SD_BRIDGE_PORT

SERVER_NAME = "dcc-mcp-substancedesigner"
SERVER_VERSION = __version__
DEFAULT_MCP_PORT = 8766
DEFAULT_GATEWAY_PORT = 9765
_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_DCC_NAME = "substancedesigner"
_DEFAULT_SKILLS = ("substance-designer",)
_SERVER: Optional["SubstanceDesignerMcpServer"] = None


@dataclass
class SubstanceDesignerServerOptions:
    """Adapter-local options for the Substance Designer MCP server."""

    port: int = DEFAULT_MCP_PORT
    sd_host: str = "127.0.0.1"
    sd_port: int = DEFAULT_SD_BRIDGE_PORT
    extra_skill_paths: Optional[List[str]] = None
    server_name: str = SERVER_NAME
    server_version: str = SERVER_VERSION
    gateway_port: Optional[int] = DEFAULT_GATEWAY_PORT
    registry_dir: Optional[str] = None
    dcc_version: Optional[str] = None
    scene: Optional[str] = None
    dispatcher: Optional[Any] = None
    execution_bridge: Optional[Any] = None
    enable_gateway_failover: bool = True
    eager_builtin_skills: bool = True

    def make_bridge_client(self) -> SubstanceDesignerBridgeClient:
        """Create a client for the Substance Designer plugin bridge."""
        return SubstanceDesignerBridgeClient(host=self.sd_host, port=self.sd_port)

    def apply_bridge_environment(self) -> None:
        """Expose bridge settings to skill scripts and subprocess fallbacks."""
        os.environ[ENV_SD_BRIDGE_HOST] = self.sd_host
        os.environ[ENV_SD_BRIDGE_PORT] = str(self.sd_port)
        os.environ.setdefault("DCC_MCP_PYTHON_EXECUTABLE", sys.executable)

    def to_core_options(self) -> Any:
        """Convert to dcc-mcp-core options when the shared package is installed."""
        try:
            from dcc_mcp_core._server.options import DccServerOptions
        except ModuleNotFoundError as exc:
            raise RuntimeError("dcc-mcp-core is required to start the MCP server") from exc

        return DccServerOptions.from_env(
            dcc_name=_DCC_NAME,
            builtin_skills_dir=_BUILTIN_SKILLS_DIR,
            port=self.port,
            server_name=self.server_name,
            server_version=self.server_version,
            gateway_port=self.gateway_port,
            registry_dir=self.registry_dir,
            dcc_version=self.dcc_version,
            scene=self.scene,
            enable_gateway_failover=self.enable_gateway_failover,
            dispatcher=self.dispatcher,
            execution_bridge=self.execution_bridge or _make_execution_bridge(self.dispatcher),
        )


class SubstanceDesignerMcpServer:
    """Substance Designer MCP server backed by dcc-mcp-core."""

    def __init__(self, options: Optional[SubstanceDesignerServerOptions] = None, **kwargs: Any) -> None:
        self.options = options or SubstanceDesignerServerOptions(**kwargs)
        self.options.apply_bridge_environment()
        self.bridge_client = self.options.make_bridge_client()
        try:
            from dcc_mcp_core.server_base import DccServerBase
        except ModuleNotFoundError as exc:
            raise RuntimeError("dcc-mcp-core is required to create the MCP server") from exc

        core_options = self.options.to_core_options()
        self._core_server = DccServerBase(options=core_options)
        self._apply_gateway_port_override()
        self._register_authoring_reference_resources()

    @property
    def port(self) -> int:
        """TCP port used by the MCP endpoint."""
        handle = getattr(self._core_server, "_handle", None)
        if handle is not None:
            try:
                return int(handle.port)
            except Exception:
                pass
        return int(self.options.port)

    @property
    def mcp_url(self) -> str:
        """Return the MCP Streamable HTTP endpoint URL."""
        return f"http://127.0.0.1:{self.port}/mcp"

    def _apply_gateway_port_override(self) -> None:
        """Force adapter-resolved gateway settings onto the core HTTP config.

        Some dcc-mcp-core versions construct ``McpHttpConfig`` with its own
        gateway default before applying resolved options, so ``0``/``None`` can
        otherwise unintentionally leave the built-in default gateway enabled.
        """
        config = getattr(self._core_server, "_config", None)
        if config is None or self.options.gateway_port is None:
            return
        config.gateway_port = int(self.options.gateway_port)

    def start(self) -> "SubstanceDesignerMcpServer":
        """Start the core-backed MCP server."""
        self.register_builtin_actions()
        self._core_server.start()
        return self

    def register_builtin_actions(self) -> None:
        """Discover adapter skills and expose all adapter-owned tools at startup."""
        self._core_server.register_builtin_actions(
            extra_skill_paths=self.options.extra_skill_paths,
            include_bundled=False,
        )
        if self.options.eager_builtin_skills:
            for skill_name in _DEFAULT_SKILLS:
                self._core_server.load_skill(skill_name)
        self._apply_startup_tool_visibility()

    def _register_authoring_reference_resources(self) -> None:
        """Publish static graph authoring references as MCP resources."""
        register_resource_producer = getattr(self._core_server, "register_resource_producer", None)
        if not callable(register_resource_producer):
            return
        register_resource_producer(AUTHORING_PREFIX, SubstanceAuthoringReferenceProducer())

    def _apply_startup_tool_visibility(self) -> None:
        """Expose every adapter-owned tool and hide generic bundled tools."""
        registry = getattr(getattr(self._core_server, "_server", None), "registry", None)
        if registry is None:
            return

        for action in registry.list_actions():
            name = _action_name(action)
            if not name:
                continue
            if name.startswith("substance_designer_"):
                registry.set_action_enabled(name, True)
            else:
                registry.set_action_enabled(name, False)

    def shutdown(self) -> None:
        """Stop the core server if it has been started."""
        backend_port = self.port
        handle = getattr(self._core_server, "_handle", None)
        is_gateway = bool(getattr(handle, "is_gateway", False)) if handle is not None else False
        gateway_port = int(self.options.gateway_port or 0) if is_gateway else 0
        if hasattr(self._core_server, "stop"):
            self._core_server.stop()
        elif hasattr(self._core_server, "shutdown"):
            self._core_server.shutdown()
        _wait_for_loopback_ports_released(backend_port, gateway_port)

    def list_actions(self) -> list[Any]:
        """List registered MCP actions for this adapter."""
        registry = getattr(getattr(self._core_server, "_server", None), "registry", None)
        if registry is not None and hasattr(registry, "list_actions_enabled"):
            return [
                action
                for action in registry.list_actions_enabled()
                if _action_dcc(action) == _DCC_NAME and _action_name(action).startswith("substance_designer_")
            ]
        return self._core_server.list_actions(_DCC_NAME)

    def list_skills(self) -> list[Any]:
        """List discovered skills."""
        return self._core_server.list_skills()


def start_server(**kwargs: Any) -> SubstanceDesignerMcpServer:
    """Create and start the process-global Substance Designer MCP server."""
    global _SERVER
    _SERVER = SubstanceDesignerMcpServer(**kwargs)
    return _SERVER.start()


def stop_server() -> None:
    """Stop the process-global Substance Designer MCP server."""
    global _SERVER
    if _SERVER is not None:
        _SERVER.shutdown()
        _SERVER = None


def get_server() -> Optional[SubstanceDesignerMcpServer]:
    """Return the process-global server, if one is active."""
    return _SERVER


def _make_execution_bridge(dispatcher: Any | None = None) -> Any:
    """Create the in-process skill execution bridge for adapter-owned scripts."""
    try:
        from dcc_mcp_core._server.inprocess_executor import HostExecutionBridge
    except ModuleNotFoundError as exc:
        raise RuntimeError("dcc-mcp-core is required to create the in-process executor") from exc

    return HostExecutionBridge(dispatcher=dispatcher, runner=_run_substance_skill_script)


def _run_substance_skill_script(script_path: str, params: Mapping[str, Any]) -> Any:
    """Run a bundled skill script in-process with sibling helper imports available."""
    try:
        from dcc_mcp_core._server.inprocess_executor import run_skill_script
    except ModuleNotFoundError as exc:
        raise RuntimeError("dcc-mcp-core is required to run skill scripts in-process") from exc

    script_dir = str(Path(script_path).resolve().parent)
    with _prepend_sys_path(script_dir):
        return run_skill_script(script_path, dict(params))


@contextmanager
def _prepend_sys_path(path: str):
    """Temporarily put *path* first on ``sys.path``."""
    sys.path.insert(0, path)
    try:
        yield
    finally:
        try:
            sys.path.remove(path)
        except ValueError:
            pass


def _action_name(action: Any) -> str:
    """Return a registry action name from dict or object shapes."""
    if isinstance(action, dict):
        return str(action.get("name") or "")
    return str(getattr(action, "name", ""))


def _action_dcc(action: Any) -> str:
    """Return a registry action DCC from dict or object shapes."""
    if isinstance(action, dict):
        return str(action.get("dcc") or "")
    return str(getattr(action, "dcc", ""))


def _wait_for_loopback_ports_released(*ports: int, timeout: float = 5.0) -> None:
    """Wait until just-stopped loopback listeners are actually re-bindable.

    dcc-mcp-core may run the HTTP listener on a dedicated OS thread and return
    from shutdown before that thread has fully exited. On Windows with WSL2
    mirrored networking, exiting immediately after that can leave localhost
    forwarding with a stale reservation for the gateway port.
    """
    targets = sorted({int(port) for port in ports if port and port > 0})
    if not targets:
        return

    deadline = time.monotonic() + timeout
    pending = set(targets)
    while pending and time.monotonic() < deadline:
        pending = {port for port in pending if not _loopback_port_can_bind(port)}
        if pending:
            time.sleep(0.05)


def _loopback_port_can_bind(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True
