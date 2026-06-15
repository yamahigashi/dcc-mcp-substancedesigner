"""Type aliases and protocols for the bridge server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..json_types import JsonMap, JsonValue


class CommandDispatcher(Protocol):
    """Protocol for command handlers used by the bridge server."""

    def dispatch(self, cmd_type: str, params: JsonMap) -> JsonValue:
        """Dispatch a validated command payload."""
        ...


class MainThreadRunner(Protocol):
    """Protocol for running command dispatch on the Substance Designer main thread."""

    def __call__(self, fn: Callable[[str, JsonMap], JsonValue], cmd_type: str, params: JsonMap) -> JsonValue:
        """Run a command dispatch callable on the host main thread."""
        ...


class JsonFallbackValue(Protocol):
    """Protocol for values that can fall back to string JSON encoding."""

    def __str__(self) -> str:
        """Return a fallback string representation."""
        ...
