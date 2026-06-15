"""Protocols and aliases for explicit Python execution support."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeAlias

from ..json_types import JsonValue

ExecutionResult: TypeAlias = dict[str, JsonValue]


class ReprFallback(Protocol):
    """Protocol for values that can be represented as diagnostic text."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class UiManager(Protocol):
    """Protocol for the Substance Designer UI manager method used here."""

    def openResourceInEditor(self, graph: ReprFallback) -> None:
        """Open a graph resource in the editor."""
        ...


class SDApplication(Protocol):
    """Protocol for the Substance Designer application methods used here."""

    def getPackageMgr(self) -> ReprFallback:
        """Return the host package manager."""
        ...

    def getUIMgr(self) -> UiManager:
        """Return the host UI manager."""
        ...


class SDContext(Protocol):
    """Protocol for the Substance Designer context method used here."""

    def getSDApplication(self) -> SDApplication:
        """Return the host application."""
        ...


class SDModule(Protocol):
    """Protocol for the Substance Designer module surface used here."""

    def getContext(self) -> SDContext:
        """Return the host context."""
        ...


NamespaceValue: TypeAlias = ReprFallback | Callable[[ReprFallback], None]
