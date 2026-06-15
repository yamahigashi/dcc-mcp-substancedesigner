"""Protocols and aliases for node helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, TypeAlias

from ..host.host_types import (
    HostConnection,
    HostDefinition,
    HostNode,
    HostProperty,
    ReprFallback,
)
from ..json_types import JsonScalar, JsonValue
from ..library.library_types import LibraryResource

PropertyInfo: TypeAlias = dict[str, JsonScalar]
NodePropertyInfo: TypeAlias = dict[str, JsonValue]
NodeDetail: TypeAlias = dict[str, JsonValue]
NestedGraphRef: TypeAlias = dict[str, JsonScalar]
InstanceRef: TypeAlias = dict[str, str]
HostGetter: TypeAlias = Callable[[], JsonScalar | None]
PositionInput: TypeAlias = JsonValue


class DetailConnection(HostConnection, Protocol):
    """Protocol for input property connections used by node detail responses."""

    def getInputPropertyNode(self) -> "DetailNode | None":
        """Return the source node for the connection."""
        ...

    def getInputProperty(self) -> HostProperty | None:
        """Return the source property for the connection."""
        ...


class DetailNode(HostNode, Protocol):
    """Protocol for nodes serialized by ``get_node_info``."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getPropertyValue(self, prop: HostProperty) -> ReprFallback | None:
        """Return a property value."""
        ...

    def getPropertyConnections(self, prop: HostProperty) -> Iterable[DetailConnection] | None:
        """Return property connections."""
        ...


class ValueSerializer(Protocol):
    """Protocol for SDValue serializers."""

    def __call__(self, value: ReprFallback | None) -> JsonValue:
        """Serialize an SDValue-like value."""
        ...


class GraphPackageSource(Protocol):
    """Protocol for graph values that can expose package paths."""

    def getUrl(self) -> str:
        """Return the graph URL."""
        ...


class MutableNode(HostNode, Protocol):
    """Protocol for nodes that can be mutated by authoring tools."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...


class MutableGraph(Protocol):
    """Protocol for graphs that support node mutation."""

    def getNodeDefinitions(self) -> Iterable[HostDefinition]:
        """Return available node definitions."""
        ...

    def newNode(self, definition_id: str) -> MutableNode | None:
        """Create a node by definition id."""
        ...

    def newInstanceNode(self, resource: LibraryResource) -> MutableNode | None:
        """Create an instance node from a resource."""
        ...

    def deleteNode(self, node: MutableNode) -> None:
        """Delete a node."""
        ...


class ResourcePackage(Protocol):
    """Protocol for packages that can resolve graph resources."""

    def findResourceFromUrl(self, url: str) -> LibraryResource | None:
        """Find a resource by URL."""
        ...


class ResourcePackageManager(Protocol):
    """Protocol for package managers used by instance node creation."""

    def getPackages(self) -> Iterable[ResourcePackage]:
        """Return packages available to the host."""
        ...
