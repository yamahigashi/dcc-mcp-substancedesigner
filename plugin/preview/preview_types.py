"""Protocols and aliases for preview helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, TypeAlias

from sd.api.sdproperty import SDPropertyCategory

from ..graph.graph_types import GraphOutputSizeHost
from ..json_types import JsonMap, JsonValue
from ..node.node_types import GraphPackageSource
from ..parameters.parameter_types import SettableSDValue

__all__ = [
    "ClassNamed",
    "GraphOutputSizeHost",
    "HashPreviewNode",
    "NodeDefinitionReader",
    "OutputProperty",
    "PositionValue",
    "PreviewCache",
    "PreviewHashEntry",
    "PreviewInputEntry",
    "PreviewNode",
    "PreviewPropertyGraph",
    "PropertyGraphPreviewNode",
    "QtCoreImageModule",
    "QtGuiImageModule",
    "QtImageModules",
    "ReprFallback",
    "SDPropertyCategory",
    "SDTypeLike",
    "SaveMethod",
    "SourcePreviewNode",
    "TemporaryOutputGraph",
    "TemporaryOutputNode",
    "TextureConvertible",
    "ValueContainer",
    "ValueSerializer",
]

SaveMethod: TypeAlias = Callable[[str], None]
QtImageModules: TypeAlias = tuple["QtGuiImageModule", "QtCoreImageModule"]
PreviewInputEntry: TypeAlias = dict[str, JsonValue]
PreviewHashEntry: TypeAlias = dict[str, JsonValue]
PreviewCache: TypeAlias = dict[str, JsonMap]
NodeDefinitionReader: TypeAlias = Callable[["HashPreviewNode"], str]
ValueSerializer: TypeAlias = Callable[["ReprFallback"], JsonValue]


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


PositionValue: TypeAlias = tuple[float, float] | ReprFallback


class SDTypeLike(Protocol):
    """Protocol for SD type values used by output properties."""

    def getId(self) -> str:
        """Return the type identifier."""
        ...


class ClassNamed(Protocol):
    """Protocol for host values exposing a Substance Designer class name."""

    def getClassName(self) -> str:
        """Return the host class name."""
        ...


class OutputProperty(Protocol):
    """Protocol for output properties used by node previews."""

    def getId(self) -> str:
        """Return the property identifier."""
        ...

    def getType(self) -> SDTypeLike | None:
        """Return the property type."""
        ...


class PreviewNode(Protocol):
    """Protocol for nodes that expose preview output properties."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getProperties(self, category: int) -> Iterable[OutputProperty]:
        """Return properties for the requested category."""
        ...


class SourcePreviewNode(PreviewNode, Protocol):
    """Protocol for source nodes used by temporary preview outputs."""

    def newPropertyConnectionFromId(
        self,
        output_id: str,
        target_node: "TemporaryOutputNode",
        target_input_id: str,
    ) -> ReprFallback | None:
        """Connect a source output to a target input."""
        ...


class TemporaryOutputNode(PreviewNode, Protocol):
    """Protocol for temporary output nodes used during preview fallback."""

    def setPosition(self, position: PositionValue) -> None:
        """Set the node position."""
        ...

    def setAnnotationPropertyValueFromId(self, property_id: str, value: SettableSDValue) -> None:
        """Set an annotation property value."""
        ...

    def getPropertyValue(self, prop: OutputProperty) -> ReprFallback | None:
        """Return the value for an output property."""
        ...


class TemporaryOutputGraph(Protocol):
    """Protocol for graph APIs used by temporary preview outputs."""

    def newNode(self, definition_id: str) -> TemporaryOutputNode | None:
        """Create a new node."""
        ...

    def compute(self) -> None:
        """Compute the graph."""
        ...

    def deleteNode(self, node: TemporaryOutputNode) -> None:
        """Delete a node."""
        ...


class TextureConvertible(Protocol):
    """Protocol for values that can produce an SD texture."""

    def toSDTexture(self) -> ReprFallback:
        """Return a texture value."""
        ...


class ValueContainer(Protocol):
    """Protocol for SDValue-like wrappers that expose a raw value."""

    def get(self) -> ReprFallback:
        """Return a wrapped host value."""
        ...


class HashPreviewConnection(Protocol):
    """Protocol for connections used in preview hash traversal."""

    def getInputPropertyNode(self) -> "HashPreviewNode | None":
        """Return the source node for this connection."""
        ...

    def getInputProperty(self) -> OutputProperty | None:
        """Return the source property for this connection."""
        ...


class PreviewGraph(Protocol):
    """Protocol for graphs used in preview hash traversal."""

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        ...

    def getProperties(self, category: int) -> Iterable[OutputProperty]:
        """Return graph properties for a category."""
        ...

    def getPropertyValue(self, prop: OutputProperty) -> ReprFallback | None:
        """Return a graph property value."""
        ...


class HashPreviewNode(Protocol):
    """Protocol for nodes used in preview hash traversal."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getProperties(self, category: int) -> Iterable[OutputProperty]:
        """Return node properties for a category."""
        ...

    def getPropertyConnections(self, prop: OutputProperty) -> Iterable[HashPreviewConnection] | None:
        """Return inbound connections for a property."""
        ...

    def getPropertyValue(self, prop: OutputProperty) -> ReprFallback | None:
        """Return the current property value."""
        ...


class PreviewPropertyGraph(Protocol):
    """Protocol for property-backed nested graphs used in preview hashing."""

    def getNodes(self) -> Iterable[HashPreviewNode]:
        """Return nested graph nodes."""
        ...


class PropertyGraphPreviewNode(HashPreviewNode, Protocol):
    """Protocol for nodes exposing property-backed nested graphs."""

    def getPropertyGraph(self, prop: OutputProperty) -> PreviewPropertyGraph | None:
        """Return a property-backed nested graph."""
        ...


class RenderGraph(GraphOutputSizeHost, TemporaryOutputGraph, GraphPackageSource, PreviewGraph, Protocol):
    """Protocol for graphs used during preview rendering."""


class NodeDefinition(Protocol):
    """Protocol for node definitions."""

    def getId(self) -> str:
        """Return the definition identifier."""
        ...


class NodeWithDefinition(Protocol):
    """Protocol for nodes that expose a definition."""

    def getDefinition(self) -> NodeDefinition | None:
        """Return the node definition."""
        ...


class RenderNode(SourcePreviewNode, HashPreviewNode, NodeWithDefinition, Protocol):
    """Protocol for nodes used during preview rendering."""


class QtTransformNamespace(Protocol):
    """Protocol for Qt transformation constants used during preview resizing."""

    IgnoreAspectRatio: int
    SmoothTransformation: int


class QtCoreImageModule(Protocol):
    """Protocol for the QtCore subset needed by preview resizing."""

    Qt: QtTransformNamespace


class QtImage(Protocol):
    """Protocol for the QImage methods used by preview resizing."""

    def isNull(self) -> bool:
        """Return whether the image is empty or invalid."""
        ...

    def width(self) -> int:
        """Return the image width in pixels."""
        ...

    def height(self) -> int:
        """Return the image height in pixels."""
        ...

    def pixelColor(self, x: int, y: int) -> "QtColor":
        """Return the color at a pixel."""
        ...

    def scaled(self, width: int, height: int, aspect_mode: int, transform_mode: int) -> "QtImage":
        """Return a resized image."""
        ...

    def save(self, image_path: str, image_format: str) -> bool:
        """Save the image to disk."""
        ...


class QtColor(Protocol):
    """Protocol for pixel color values used by preview stats."""

    def red(self) -> int:
        """Return red channel."""
        ...

    def green(self) -> int:
        """Return green channel."""
        ...

    def blue(self) -> int:
        """Return blue channel."""
        ...


class QtGuiImageModule(Protocol):
    """Protocol for the QtGui subset needed by preview resizing."""

    def QImage(self, image_path: str) -> QtImage:
        """Load a QImage from disk."""
        ...
