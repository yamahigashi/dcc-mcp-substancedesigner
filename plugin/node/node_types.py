"""Protocols and aliases for node helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Protocol, TypeAlias

from ..json_types import JsonScalar, JsonValue
from ..library.library_types import LibraryResource

if TYPE_CHECKING:
    from sd.api.sdbasetypes import float2

    from ..parameters.parameter_types import SettableSDValue

PropertyInfo: TypeAlias = dict[str, JsonScalar]
NodePropertyInfo: TypeAlias = dict[str, JsonValue]
NodeDetail: TypeAlias = dict[str, JsonValue]
NestedGraphRef: TypeAlias = dict[str, JsonScalar]
InstanceRef: TypeAlias = dict[str, str]
HostGetter: TypeAlias = Callable[[], JsonScalar | None]
PositionInput: TypeAlias = JsonValue


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class HostDefinition(Protocol):
    """Protocol for node definitions."""

    def getId(self) -> str:
        """Return the definition identifier."""
        ...


class HostResource(Protocol):
    """Protocol for referenced graph resources."""

    def getIdentifier(self) -> str:
        """Return the resource identifier."""
        ...

    def getUrl(self) -> str:
        """Return the resource URL."""
        ...

    def getClassName(self) -> str:
        """Return the resource class name when available."""
        ...


class HostPackage(Protocol):
    """Protocol for host packages."""

    def getFilePath(self) -> str:
        """Return the package file path."""
        ...


class HostPosition(Protocol):
    """Protocol for node position values."""

    x: float
    y: float


class HostPropertyType(Protocol):
    """Protocol for host property type values."""

    def getId(self) -> str:
        """Return the type identifier."""
        ...


class HostProperty(Protocol):
    """Protocol for host properties."""

    def getId(self) -> str:
        """Return the property identifier."""
        ...

    def getType(self) -> HostPropertyType | None:
        """Return the property type."""
        ...


class HostGraph(Protocol):
    """Protocol for graph values used by node helpers."""

    def getClassName(self) -> str:
        """Return the graph class name."""
        ...


class HostNode(Protocol):
    """Protocol for node values used by node helpers."""

    def getDefinition(self) -> HostDefinition | None:
        """Return the node definition."""
        ...

    def getReferencedResource(self) -> HostResource | None:
        """Return the referenced graph resource when present."""
        ...

    def getPackage(self) -> HostPackage | None:
        """Return the owning package when present."""
        ...

    def getPosition(self) -> HostPosition:
        """Return the node position."""
        ...

    def getProperties(self, category: int) -> Iterable[HostProperty]:
        """Return properties for a category."""
        ...

    def getPropertyGraph(self, prop: HostProperty) -> HostGraph | None:
        """Return a nested graph for a property when present."""
        ...


class HostConnection(Protocol):
    """Protocol for connection values used by inspection helpers."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


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

    def setPosition(self, position: float2) -> None:
        """Set the node position."""
        ...

    def setAnnotationPropertyValueFromId(self, parameter_id: str, value: SettableSDValue) -> None:
        """Set an annotation parameter value."""
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
