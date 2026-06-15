"""Tests for plugin-side SDValue serialization helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERIALIZATION_PATH = REPO_ROOT / "plugin" / "sd_serialization.py"


class FakeValue:
    """Fake SDValue wrapper."""

    def __init__(self, raw: FakeRawValue) -> None:
        """Store a raw fake value."""
        self.raw = raw

    def get(self) -> FakeRawValue:
        """Return the raw fake value."""
        return self.raw


class FakeRawValue:
    """Base fake raw value."""


class FakeVector(FakeRawValue):
    """Fake vector value."""

    x = 1
    y = 2
    z = 3


class FakeColor(FakeRawValue):
    """Fake color value."""

    r = 0.1
    g = 0.2
    b = 0.3
    a = 1.0


class FakeSequence(FakeRawValue):
    """Fake SD sequence value."""

    def getSize(self) -> int:
        """Return the fake sequence size."""
        return 2

    def getItem(self, index: int) -> str:
        """Return a fake item."""
        return "item-{}".format(index)


class FakeUsage:
    """Fake raw SDUsage value."""

    def __init__(self, name: str, components: str, color_space: str) -> None:
        """Store usage metadata."""
        self.name = name
        self.components = components
        self.color_space = color_space

    def getName(self) -> str:
        """Return usage name."""
        return self.name

    def getComponents(self) -> str:
        """Return usage components."""
        return self.components

    def getColorSpace(self) -> str:
        """Return usage color space."""
        return self.color_space


class FakeUsageArray(FakeRawValue):
    """Fake SDValueArray<SDTypeUsage> raw value."""

    def __init__(self) -> None:
        """Create a single usage item."""
        self.items = [FakeValue(FakeUsage("baseColor", "RGBA", "sRGB"))]

    def getSize(self) -> int:
        """Return item count."""
        return len(self.items)

    def getItem(self, index: int) -> FakeValue:
        """Return usage value item."""
        return self.items[index]


def test_serialize_sd_value_serializes_vectors() -> None:
    module = _load_serialization_module()

    assert module.serialize_sd_value(FakeValue(FakeVector())) == {"x": 1, "y": 2, "z": 3}


def test_serialize_sd_value_serializes_colors() -> None:
    module = _load_serialization_module()

    assert module.serialize_sd_value(FakeValue(FakeColor())) == {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0}


def test_serialize_sd_value_serializes_sequences() -> None:
    module = _load_serialization_module()

    assert module.serialize_sd_value(FakeValue(FakeSequence())) == ["item-0", "item-1"]


def test_serialize_sd_value_preserves_usage_array_metadata() -> None:
    module = _load_serialization_module()

    assert module.serialize_sd_value(FakeValue(FakeUsageArray())) == [
        {"name": "baseColor", "components": "RGBA", "color_space": "sRGB"}
    ]


def _load_serialization_module():
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    previous_package = sys.modules.get("plugin")
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.sd_serialization",
        "plugin.sd_serialization_types",
        "plugin.sd_serialization_values",
    ]:
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location("plugin.sd_serialization", SERIALIZATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules["plugin.sd_serialization"] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        for module_name in [
            "plugin.sd_serialization",
            "plugin.sd_serialization_types",
            "plugin.sd_serialization_values",
        ]:
            sys.modules.pop(module_name, None)
        if previous_package is None:
            sys.modules.pop("plugin", None)
        else:
            sys.modules["plugin"] = previous_package
    return module
