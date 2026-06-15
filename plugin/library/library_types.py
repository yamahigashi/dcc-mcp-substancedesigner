"""Protocols and aliases for library node helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeAlias

from ..host.host_types import HostGraph, HostPackage, HostPackageManager, HostResource, ReprFallback
from ..json_types import JsonScalar, JsonValue

PositionInput: TypeAlias = Sequence[JsonScalar]
LibraryCache: TypeAlias = dict[str, str]
LibraryNodeInfo: TypeAlias = dict[str, JsonValue]


PositionValue: TypeAlias = tuple[float, float] | ReprFallback
LibraryResource: TypeAlias = HostResource
LibraryPackage: TypeAlias = HostPackage
LibraryPackageManager: TypeAlias = HostPackageManager


class LibraryNode(Protocol):
    """Protocol for created library instance nodes."""

    def setPosition(self, position: PositionValue) -> None:
        """Set the node position."""
        ...


class LibraryGraph(Protocol):
    """Protocol for graphs that can create library instance nodes."""

    def newInstanceNode(self, resource: LibraryResource) -> LibraryNode | None:
        """Create an instance node from a resource."""
        ...


HostLibraryGraph: TypeAlias = HostGraph
