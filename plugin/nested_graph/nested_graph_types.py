"""Protocols and JSON aliases for nested graph helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol, TypeAlias

from ..json_types import JsonValue
from ..library.library_types import LibraryResource
from ..parameters.parameter_types import SettableSDValue

NestedNodeState: TypeAlias = dict[str, JsonValue]
NestedConnectionState: TypeAlias = dict[str, JsonValue]
NestedGraphState: TypeAlias = dict[str, JsonValue]
OutputGetter: TypeAlias = Callable[[], "NestedNode | Sequence[NestedNode] | OutputNodeCollection | None"]
NodeDefinitionGetter: TypeAlias = Callable[["NestedNode"], str]
NodePositionGetter: TypeAlias = Callable[["NestedNode"], list[float]]
ValueSerializer: TypeAlias = Callable[["ReprFallback"], JsonValue]
ParameterSetter: TypeAlias = Callable[["MutableNestedNode", dict[str, JsonValue]], dict[str, JsonValue] | None]
NodeConnector: TypeAlias = Callable[["MutableNestedGraph", "MutableNestedNode", str, "MutableNestedNode", str], None]
GraphResolver: TypeAlias = Callable[[str | None], "NestedOwnerGraph"]
NodeFinder: TypeAlias = Callable[["NestedOwnerGraph", str], "PropertyGraphOwner"]


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


PositionValue: TypeAlias = tuple[float, float] | ReprFallback


class NestedProperty(Protocol):
    """Protocol for nested graph properties."""

    def getId(self) -> str:
        """Return the property identifier."""
        ...

    def getType(self) -> ReprFallback:
        """Return the property type."""
        ...


class SDTypeValue(Protocol):
    """Protocol for SDType values used to create owner input properties."""

    def getId(self) -> str:
        """Return the type identifier."""
        ...


class NestedConnection(Protocol):
    """Protocol for nested graph connections."""

    def getInputPropertyNode(self) -> "NestedNode | None":
        """Return the source node for a connection."""
        ...

    def getInputProperty(self) -> NestedProperty | None:
        """Return the source property for a connection."""
        ...


class NestedNode(Protocol):
    """Protocol for nodes used in nested graph inspection."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getProperties(self, category: int) -> Iterable[NestedProperty]:
        """Return node properties for a category."""
        ...

    def getPropertyConnections(self, prop: NestedProperty) -> Iterable[NestedConnection] | None:
        """Return property connections."""
        ...

    def getPropertyValue(self, prop: NestedProperty) -> ReprFallback | None:
        """Return a property value."""
        ...


class MutableNestedNode(NestedNode, Protocol):
    """Protocol for nested graph nodes created during apply."""

    def getPropertyFromId(self, property_id: str, category: int) -> NestedProperty | None:
        """Return a property by identifier and category."""
        ...

    def setPosition(self, position: PositionValue) -> None:
        """Set the node position."""
        ...

    def newProperty(self, property_id: str, property_type: SDTypeValue, category: int) -> NestedProperty | None:
        """Create a property by identifier, type, and category."""
        ...

    def setPropertyValue(self, prop: NestedProperty, value: SettableSDValue) -> None:
        """Set a property value."""
        ...

    def setInputPropertyValueFromId(self, property_id: str, value: SettableSDValue) -> None:
        """Set an input property value by identifier."""
        ...

    def setPropertyAnnotationValueFromId(
        self, prop: NestedProperty, annotation_id: str, value: SettableSDValue
    ) -> None:
        """Set a property annotation value."""
        ...

    def setAnnotationPropertyValueFromId(self, property_id: str, value: SettableSDValue) -> None:
        """Set an annotation property value by identifier."""
        ...

    def getPropertyGraph(self, prop: NestedProperty) -> "MutableNestedGraph | None":
        """Return the nested graph for a property."""
        ...

    def deletePropertyGraph(self, prop: NestedProperty) -> None:
        """Delete the nested graph for a property."""
        ...

    def newPropertyGraph(self, prop: NestedProperty, graph_type: str) -> "MutableNestedGraph | None":
        """Create a nested graph for a property."""
        ...

    def getReferencedResource(self) -> LibraryResource | "MutableNestedGraph" | None:
        """Return the referenced package resource or FX-Map graph."""
        ...


class NodeDefinition(Protocol):
    """Protocol for nested graph node definitions."""

    def getId(self) -> str:
        """Return the node definition identifier."""
        ...


class OwnerNode(Protocol):
    """Protocol for nodes that own nested graph properties."""

    def getIdentifier(self) -> str:
        """Return the owner node identifier."""
        ...

    def getPropertyFromId(self, property_id: str, category: int) -> NestedProperty | None:
        """Return a property by identifier and category."""
        ...

    def getProperties(self, category: int) -> Iterable[NestedProperty]:
        """Return properties for a category."""
        ...

    def getPropertyValue(self, prop: NestedProperty) -> ReprFallback | None:
        """Return a property value."""
        ...


class PropertyGraphOwner(OwnerNode, Protocol):
    """Protocol for owner nodes that can read and rebuild nested property graphs."""

    def newProperty(self, property_id: str, property_type: SDTypeValue, category: int) -> NestedProperty | None:
        """Create a property by identifier, type, and category."""
        ...

    def setPropertyValue(self, prop: NestedProperty, value: SettableSDValue) -> None:
        """Set a property value."""
        ...

    def setInputPropertyValueFromId(self, property_id: str, value: SettableSDValue) -> None:
        """Set an input property value by identifier."""
        ...

    def setPropertyAnnotationValueFromId(
        self, prop: NestedProperty, annotation_id: str, value: SettableSDValue
    ) -> None:
        """Set a property annotation value."""
        ...

    def getPropertyGraph(self, prop: NestedProperty) -> "MutableNestedGraph | None":
        """Return the nested graph for a property."""
        ...

    def deletePropertyGraph(self, prop: NestedProperty) -> None:
        """Delete the nested graph for a property."""
        ...

    def newPropertyGraph(self, prop: NestedProperty, graph_type: str) -> "MutableNestedGraph | None":
        """Create a nested graph for a property."""
        ...

    def getReferencedResource(self) -> "MutableNestedGraph | None":
        """Return a node-referenced resource such as an FX-Map graph."""
        ...


class OutputNodeCollection(Protocol):
    """Protocol for host collection values returned by output-node APIs."""

    def getSize(self) -> int:
        """Return the collection size."""
        ...

    def getItem(self, index: int) -> NestedNode | None:
        """Return an item by index."""
        ...


class NestedGraph(Protocol):
    """Protocol for nested graph values."""

    def getNodes(self) -> Iterable[NestedNode]:
        """Return nested graph nodes."""
        ...

    def getClassName(self) -> str:
        """Return the graph class name."""
        ...


class NestedOwnerGraph(Protocol):
    """Protocol for the parent graph that owns a nested graph target."""

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        ...


class MutableNestedGraph(NestedGraph, Protocol):
    """Protocol for nested graphs that can be rebuilt."""

    def getNodes(self) -> Iterable[MutableNestedNode]:
        """Return mutable nested graph nodes."""
        ...

    def getNodeDefinitions(self) -> Iterable[NodeDefinition]:
        """Return definitions available in the nested graph."""
        ...

    def newNode(self, definition_id: str) -> MutableNestedNode | None:
        """Create a node by definition identifier."""
        ...

    def newInstanceNode(self, resource: LibraryResource) -> MutableNestedNode | None:
        """Create an instance node from a package resource."""
        ...

    def setOutputNode(self, node: MutableNestedNode, enabled: bool) -> None:
        """Mark a node as a graph output."""
        ...

    def deleteNode(self, node: MutableNestedNode) -> None:
        """Delete a node from the nested graph."""
        ...
