"""Protocols and aliases for library node helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, TypeAlias

from ..json_types import JsonScalar, JsonValue

PositionInput: TypeAlias = Sequence[JsonScalar]
LibraryCache: TypeAlias = dict[str, str]
LibraryNodeInfo: TypeAlias = dict[str, JsonValue]


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


PositionValue: TypeAlias = tuple[float, float] | ReprFallback


class LibraryResource(Protocol):
    """Protocol for package resources that can back instance nodes."""

    def getClassName(self) -> str:
        """Return the resource class name."""
        ...

    def getIdentifier(self) -> str:
        """Return the resource identifier."""
        ...

    def getUrl(self) -> str:
        """Return the resource URL."""
        ...


class LibraryPackage(Protocol):
    """Protocol for packages scanned for library graph resources."""

    def getFilePath(self) -> str:
        """Return the package file path."""
        ...

    def getChildrenResources(self, recursive: bool) -> Iterable[LibraryResource]:
        """Return child resources."""
        ...

    def findResourceFromUrl(self, url: str) -> LibraryResource | None:
        """Find a resource by URL."""
        ...


class LibraryPackageManager(Protocol):
    """Protocol for package managers exposing Substance Designer packages."""

    def getPackages(self) -> Iterable[LibraryPackage]:
        """Return all known packages."""
        ...

    def loadUserPackage(self, file_path: str) -> LibraryPackage:
        """Load a user package from disk."""
        ...


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
