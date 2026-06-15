"""Protocols and JSON aliases for graph helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol, TypeAlias

from ..host.host_types import (
    HostConnection,
    HostGraph,
    HostPackage,
    HostPackageManager,
    HostProperty,
    HostUiManager,
    ReprFallback,
)
from ..node.node_types import HostNode

if TYPE_CHECKING:
    from sd.api.sdbasetypes import float2

from sd.api.sdproperty import SDPropertyCategory
from sd.api.sdvalueint2 import SDValueInt2


class GraphDefinition(Protocol):
    """Protocol for graph node definition handles."""

    def getId(self) -> str:
        """Return the node definition identifier."""
        ...


GraphResource: TypeAlias = HostGraph


class LayoutNode(Protocol):
    """Protocol for graph nodes that can be positioned."""

    def setPosition(self, position: float2) -> None:
        """Set the graph editor position."""
        ...


PackageManager: TypeAlias = HostPackageManager
UiManager: TypeAlias = HostUiManager


class GraphFactory(Protocol):
    """Protocol for graph factory functions."""

    def __call__(self, parent: HostPackage, /) -> GraphResource:
        """Create a graph in a package."""
        ...


class HostValue(Protocol):
    """Protocol for Substance Designer value handles."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class OutputSizeProperty(Protocol):
    """Protocol for Substance Designer property handles."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class GraphOutputSizeHost(Protocol):
    """Protocol for graph APIs used by output-size helpers."""

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        ...

    def getPropertyFromId(self, property_id: str, category: SDPropertyCategory | int) -> OutputSizeProperty | None:
        """Return a graph property by identifier and category."""
        ...

    def getPropertyValue(self, property_handle: OutputSizeProperty) -> HostValue:
        """Return the current value for a graph property."""
        ...

    def getInputPropertyValueFromId(self, property_id: str) -> HostValue:
        """Return an input property value by identifier."""
        ...

    def setInputPropertyValueFromId(self, property_id: str, value: HostValue | SDValueInt2) -> None:
        """Set an input property value by identifier."""
        ...


class GraphConnection(HostConnection, Protocol):
    """Protocol for input property connections."""

    def getInputPropertyNode(self) -> "GraphNode | None":
        """Return the source node for a connection."""
        ...

    def getInputProperty(self) -> HostProperty | None:
        """Return the source output property."""
        ...


class GraphNode(HostNode, Protocol):
    """Protocol for nodes included in graph query responses."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getPropertyConnections(self, prop: HostProperty) -> Iterable[GraphConnection] | None:
        """Return input property connections."""
        ...

    def getPropertyValue(self, prop: HostProperty) -> ReprFallback | None:
        """Return a property value."""
        ...


class ScenePackage(HostPackage, Protocol):
    """Protocol for user packages listed in scene info."""

    def getChildrenResources(self, recursive: bool) -> Iterable[GraphResource]:
        """Return child resources."""
        ...


class ScenePackageManager(Protocol):
    """Protocol for package managers used by scene diagnostics."""

    def getUserPackages(self) -> Iterable[ScenePackage]:
        """Return user packages."""
        ...


class SceneUiManager(Protocol):
    """Protocol for UI managers exposing the current graph."""

    def getCurrentGraph(self) -> "QueryGraph | None":
        """Return the current graph."""
        ...


class QueryGraph(Protocol):
    """Protocol for graph resources queried for diagnostics."""

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        ...

    def getNodes(self) -> Iterable[GraphNode]:
        """Return graph nodes."""
        ...

    def getUrl(self) -> str:
        """Return the graph URL."""
        ...
