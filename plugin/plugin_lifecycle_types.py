"""Types for plugin lifecycle helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeAlias

from .bridge.bridge_types import CommandDispatcher, JsonFallbackValue, MainThreadRunner
from .json_types import JsonScalar

LogSink: TypeAlias = Callable[[str], None]
JsonDefault: TypeAlias = Callable[[JsonFallbackValue], JsonScalar]
ExceptionReporter: TypeAlias = Callable[[], None]


class ServerController(Protocol):
    """Protocol for bridge server instances managed by the plugin lifecycle."""

    def start(self) -> bool:
        """Start the bridge server."""
        ...

    def stop(self) -> None:
        """Stop the bridge server."""
        ...


class ServerFactory(Protocol):
    """Protocol for bridge server constructors."""

    def __call__(
        self,
        handler: CommandDispatcher,
        run_on_main: MainThreadRunner,
        json_default: JsonDefault,
        log: LogSink,
        version: tuple[int, int, int],
        ports: list[int],
    ) -> ServerController:
        """Create a bridge server."""
        ...
