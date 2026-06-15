"""Protocols and aliases for Substance Designer host helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import ParamSpec, Protocol, TypeAlias, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
QtCallback: TypeAlias = Callable[[], None]


class HostNode(Protocol):
    """Protocol for host graph nodes."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getDefinition(self) -> "HostDefinition | None":
        """Return the node definition."""
        ...

    def getReferencedResource(self) -> "HostResource | None":
        """Return the referenced graph resource when present."""
        ...

    def getPackage(self) -> "HostNodePackage | None":
        """Return the owning package when present."""
        ...

    def getPosition(self) -> "HostPosition":
        """Return the node graph-editor position."""
        ...

    def getProperties(self, category: int) -> Iterable["HostProperty"]:
        """Return node properties for a category."""
        ...

    def getPropertyFromId(self, property_id: str, category: int) -> "HostProperty | None":
        """Return a property by id and category."""
        ...

    def getPropertyValue(self, prop: "HostProperty") -> "ReprFallback | None":
        """Return a property value."""
        ...

    def getPropertyConnections(self, prop: "HostProperty") -> Iterable["HostConnection"] | None:
        """Return property connections."""
        ...

    def getPropertyGraph(self, prop: "HostProperty") -> "HostGraph | None":
        """Return a nested property graph."""
        ...

    def newProperty(self, property_id: str, property_type: "ReprFallback", category: int) -> "HostProperty | None":
        """Create a property."""
        ...

    def setPropertyValue(self, prop: "HostProperty", value: "HostSettableValue") -> None:
        """Set a property value."""
        ...

    def setInputPropertyValueFromId(self, property_id: str, value: "HostSettableValue") -> None:
        """Set an input property value."""
        ...

    def setAnnotationPropertyValueFromId(self, property_id: str, value: "HostSettableValue") -> None:
        """Set an annotation property value."""
        ...

    def setPropertyAnnotationValueFromId(
        self, prop: "HostProperty", annotation_id: str, value: "HostSettableValue"
    ) -> None:
        """Set a property annotation value."""
        ...

    def deletePropertyGraph(self, prop: "HostProperty") -> None:
        """Delete a nested property graph."""
        ...

    def newPropertyGraph(self, prop: "HostProperty", graph_type: str) -> "HostGraph | None":
        """Create a nested property graph."""
        ...

    def newPropertyConnectionFromId(
        self,
        output_id: str,
        target_node: "HostNode",
        target_input_id: str,
    ) -> "ReprFallback | None":
        """Create a connection to another node."""
        ...

    def deletePropertyConnections(self, prop: "HostProperty") -> None:
        """Delete property connections."""
        ...

    def setPosition(self, position: "HostPositionValue") -> None:
        """Set the node graph-editor position."""
        ...


class HostGraph(Protocol):
    """Protocol for host graph resources."""

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        ...

    def getClassName(self) -> str:
        """Return the graph class name."""
        ...

    def getNodeFromId(self, node_id: str) -> HostNode | None:
        """Return a node by identifier when the host supports direct lookup."""
        ...

    def getNodes(self) -> Iterable[HostNode]:
        """Return graph nodes."""
        ...

    def getProperties(self, category: int) -> Iterable["HostProperty"]:
        """Return graph properties for a category."""
        ...

    def newProperty(self, property_id: str, property_type: "ReprFallback", category: int) -> "HostProperty | None":
        """Create a graph property."""
        ...

    def getPropertyValue(self, prop: "HostProperty") -> "ReprFallback | None":
        """Return a graph property value."""
        ...

    def setInputPropertyValueFromId(self, property_id: str, value: "HostSettableValue") -> None:
        """Set a graph input value."""
        ...

    def getNodeDefinitions(self) -> Iterable["HostDefinition"]:
        """Return available node definitions."""
        ...

    def newNode(self, definition_id: str) -> HostNode | None:
        """Create a node by definition id."""
        ...

    def newInstanceNode(self, resource: "HostResource") -> HostNode | None:
        """Create an instance node from a resource."""
        ...

    def deleteNode(self, node: HostNode) -> None:
        """Delete a node."""
        ...

    def setOutputNode(self, node: HostNode, enabled: bool) -> None:
        """Mark a nested graph node as output."""
        ...


class HostPackage(Protocol):
    """Protocol for host packages."""

    def getFilePath(self) -> str:
        """Return the package file path."""
        ...

    def getChildrenResources(self, recursive: bool) -> Iterable[HostGraph]:
        """Return child resources."""
        ...

    def findResourceFromUrl(self, url: str) -> "HostResource | None":
        """Find a package resource by URL."""
        ...


class HostPackageManager(Protocol):
    """Protocol for host package managers."""

    def getUserPackages(self) -> Iterable[HostPackage]:
        """Return loaded user packages."""
        ...

    def getPackages(self) -> Iterable[HostPackage]:
        """Return all packages visible to the host."""
        ...


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


type HostPositionValue = tuple[float, float] | ReprFallback
type HostSettableValue = ReprFallback


class HostDefinition(Protocol):
    """Protocol for host node definitions."""

    def getId(self) -> str:
        """Return the definition identifier."""
        ...


class HostResource(Protocol):
    """Protocol for host graph resources."""

    def getIdentifier(self) -> str:
        """Return the resource identifier."""
        ...

    def getUrl(self) -> str:
        """Return the resource URL."""
        ...


class HostNodePackage(Protocol):
    """Protocol for packages attached to nodes."""

    def getFilePath(self) -> str:
        """Return the package file path."""
        ...


class HostPosition(Protocol):
    """Protocol for node position values."""

    x: float
    y: float


class HostPropertyType(Protocol):
    """Protocol for property type handles."""

    def getId(self) -> str:
        """Return the property type identifier."""
        ...


class HostProperty(Protocol):
    """Protocol for host properties."""

    def getId(self) -> str:
        """Return the property identifier."""
        ...

    def getType(self) -> HostPropertyType | None:
        """Return the property type."""
        ...


class HostConnection(Protocol):
    """Protocol for property connections."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...

    def getInputPropertyNode(self) -> HostNode | None:
        """Return the source node for a connection."""
        ...

    def getInputProperty(self) -> HostProperty | None:
        """Return the source property for a connection."""
        ...


class HostUiManager(Protocol):
    """Protocol for host UI managers."""

    def getCurrentGraph(self) -> HostGraph | None:
        """Return the current graph."""
        ...


class HostApplication(Protocol):
    """Protocol for the Substance Designer application handle."""

    def getPackageMgr(self) -> HostPackageManager:
        """Return the package manager."""
        ...

    def getUIMgr(self) -> HostUiManager:
        """Return the UI manager."""
        ...

    def getVersion(self) -> str:
        """Return the host application version."""
        ...


class QtSignal(Protocol):
    """Protocol for Qt signal objects used by the main-thread invoker."""

    def connect(self, callback: QtCallback, connection_type: int) -> None:
        """Connect a callback with the requested Qt connection type."""
        ...

    def emit(self) -> None:
        """Emit the signal."""
        ...


class QtNamespace(Protocol):
    """Protocol for QtCore.Qt constants needed by the plugin."""

    QueuedConnection: int


class QtCoreModule(Protocol):
    """Protocol for the subset of QtCore used by the plugin."""

    QObject: type
    Qt: QtNamespace

    def Signal(self) -> QtSignal:
        """Create a signal instance."""
        ...


class ScheduledInvoker(Protocol):
    """Protocol for host objects that can schedule callbacks on the main thread."""

    def schedule(self, callback: QtCallback) -> None:
        """Schedule a callback for Qt main-thread execution."""
        ...
