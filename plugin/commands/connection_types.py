"""Protocols and aliases for host-side node connections."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeAlias

from sd.api.sdproperty import SDPropertyCategory

__all__ = [
    "ConnectableNode",
    "ConnectionPayload",
    "ConnectionProperty",
    "ReprFallback",
    "SDPropertyCategory",
]


ConnectionPayload: TypeAlias = dict[str, bool | str]


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class ConnectionProperty(Protocol):
    """Protocol for node input and output properties."""

    def getId(self) -> str:
        """Return the property identifier."""
        ...


class ConnectableNode(Protocol):
    """Protocol for nodes that can be connected."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getProperties(self, category: int) -> Iterable[ConnectionProperty]:
        """Return properties for a category."""
        ...

    def newPropertyConnectionFromId(
        self,
        output_id: str,
        target_node: "ConnectableNode",
        target_input_id: str,
    ) -> ReprFallback | None:
        """Create a connection to another node."""
        ...


class DisconnectableNode(Protocol):
    """Protocol for nodes whose input connections can be deleted."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getProperties(self, category: int) -> Iterable[ConnectionProperty]:
        """Return properties for a category."""
        ...

    def getPropertyFromId(self, property_id: str, category: int) -> ConnectionProperty | None:
        """Return a property by id and category."""
        ...

    def deletePropertyConnections(self, prop: ConnectionProperty) -> None:
        """Delete connections from a property."""
        ...
