"""Runtime refresh helpers for the Substance Designer host plugin."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Protocol

from .json_types import JsonMap, JsonValue


class HandlerFactory(Protocol):
    """Factory protocol for building a refreshed command handler."""

    def __call__(self) -> "CommandHandlerLike":
        """Return a new command handler instance."""
        ...


class CommandHandlerLike(Protocol):
    """Protocol for refreshed command handlers."""

    HANDLERS: dict[str, Callable[..., JsonValue]]


class PluginServer(Protocol):
    """Protocol for the plugin bridge server global."""

    _handler: CommandHandlerLike


class PluginModule(Protocol):
    """Protocol for the root plugin module."""

    _server: PluginServer | None


def refresh_plugin_runtime(
    *,
    plugin_module: PluginModule,
    modules: Mapping[str, ModuleType] | None = None,
    reload_module: Callable[[ModuleType], ModuleType] = importlib.reload,
    command_handler_factory: HandlerFactory | None = None,
    root_package: str = "sd_mcp_plugin",
) -> JsonMap:
    """Reload plugin implementation modules and replace the active bridge handler."""
    server = getattr(plugin_module, "_server", None)
    if server is None:
        raise RuntimeError("Substance Designer MCP plugin server is not running.")
    loaded_modules = modules if modules is not None else sys.modules
    module_names = refresh_module_names(loaded_modules, root_package)
    reloaded: list[JsonValue] = []
    failed: list[JsonValue] = []
    for module_name in module_names:
        module = loaded_modules.get(module_name)
        if module is None:
            continue
        try:
            reload_module(module)
            reloaded.append(module_name)
        except Exception as exc:
            failed.append({"module": module_name, "error": str(exc)})
    if failed:
        return {
            "status": "error",
            "reloaded_count": len(reloaded),
            "reloaded": reloaded,
            "failed": failed,
        }
    if command_handler_factory is None:
        command_module = importlib.import_module("{}.commands.command_handler".format(root_package))
        command_handler_factory = command_module.CommandHandler
    handler = command_handler_factory()
    server._handler = handler
    commands = sorted(handler.HANDLERS.keys())
    return {
        "status": "refreshed",
        "reloaded_count": len(reloaded),
        "reloaded": reloaded,
        "handler_count": len(commands),
        "handler_commands": commands,
    }


def refresh_module_names(modules: Mapping[str, ModuleType], root_package: str) -> list[str]:
    """Return plugin module names in a reload order that keeps bridge sockets alive."""
    prefix = "{}.".format(root_package)
    excluded_prefixes = (
        "{}.bridge.".format(root_package),
        "{}.python_execution.".format(root_package),
    )
    excluded_names = {
        root_package,
        "{}.bridge".format(root_package),
        "{}.python_execution".format(root_package),
        "{}.host.host_runtime".format(root_package),
        "{}.plugin_lifecycle".format(root_package),
        "{}.plugin_refresh".format(root_package),
    }
    names = [
        name
        for name in modules
        if name.startswith(prefix) and name not in excluded_names and not name.startswith(excluded_prefixes)
    ]
    return sorted(names, key=refresh_sort_key)


def refresh_sort_key(module_name: str) -> tuple[int, int, str]:
    """Sort command handler last so it imports refreshed dependencies."""
    is_command_handler = module_name.endswith(".commands.command_handler")
    return (1 if is_command_handler else 0, module_name.count("."), module_name)
