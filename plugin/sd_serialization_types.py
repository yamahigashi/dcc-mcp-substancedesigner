"""Types for SDValue serialization helpers."""

from __future__ import annotations

from typing import Protocol

from .json_types import JsonScalar


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class SDValueLike(Protocol):
    """Protocol for SDValue wrappers."""

    def get(self) -> ReprFallback:
        """Return the wrapped value."""
        ...


class XYValue(Protocol):
    """Protocol for vector-like values with x and y components."""

    x: JsonScalar
    y: JsonScalar


class ZValue(Protocol):
    """Protocol for vector-like values with a z component."""

    z: JsonScalar


class WValue(Protocol):
    """Protocol for vector-like values with a w component."""

    w: JsonScalar


class RGBAValue(Protocol):
    """Protocol for color-like values with RGBA components."""

    r: JsonScalar
    g: JsonScalar
    b: JsonScalar
    a: JsonScalar


class SDSequenceValue(Protocol):
    """Protocol for Substance Designer sequence values."""

    def getSize(self) -> int:
        """Return the sequence size."""
        ...

    def getItem(self, index: int) -> ReprFallback:
        """Return an item by index."""
        ...


class SDUsageLike(Protocol):
    """Protocol for Substance Designer usage metadata values."""

    def getName(self) -> str:
        """Return usage name."""
        ...

    def getComponents(self) -> str:
        """Return usage components."""
        ...

    def getColorSpace(self) -> str:
        """Return usage color space."""
        ...
