"""Tests for plugin-side graph output-size helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_OUTPUT_SIZE_PATH = REPO_ROOT / "plugin" / "graph" / "graph_output_size.py"


class FakeSDValueInt2:
    """Fake SDValueInt2 wrapper."""

    def __init__(self, value: tuple[int, int]) -> None:
        """Store the wrapped tuple."""
        self.value = value

    @staticmethod
    def sNew(value: tuple[int, int]) -> "FakeSDValueInt2":
        """Create a fake SD value wrapper."""
        return FakeSDValueInt2(value)


class FakeGraph:
    """Fake graph that records output-size writes."""

    def __init__(self) -> None:
        """Initialize fake graph state."""
        self.values: dict[str, FakeSDValueInt2] = {}

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        return "Graph"

    def getPropertyFromId(self, property_id: str, category: type) -> None:
        """Return no property handle."""
        return None

    def getPropertyValue(self, property_handle: None) -> None:
        """Return no value."""
        return None

    def getInputPropertyValueFromId(self, property_id: str) -> FakeSDValueInt2 | None:
        """Return a stored input property value."""
        return self.values.get(property_id)

    def setInputPropertyValueFromId(self, property_id: str, value: FakeSDValueInt2) -> None:
        """Record an input property value."""
        self.values[property_id] = value


def test_set_graph_output_size_log2_returns_payload() -> None:
    """Log2 output-size helper writes the host value and returns the payload."""
    module = _load_graph_output_size_module()
    graph = FakeGraph()

    result = module.set_graph_output_size_log2(graph, 8, 9)

    assert result == {
        "graph": "Graph",
        "width_log2": 8,
        "height_log2": 9,
        "size": "256x512",
    }
    assert graph.values["$outputsize"].value == (8, 9)


def test_set_graph_output_size_value_converts_pixels_to_log2() -> None:
    """Pixel output-size helper converts dimensions to log2 values."""
    module = _load_graph_output_size_module()
    graph = FakeGraph()

    module.set_graph_output_size_value(graph, 1024, 2048)

    assert graph.values["$outputsize"].value == (10, 11)


def test_set_graph_output_size_pixels_accepts_common_size_forms() -> None:
    """Pixel helper accepts WIDTHxHEIGHT text and size objects."""
    module = _load_graph_output_size_module()
    graph = FakeGraph()

    text_result = module.set_graph_output_size_pixels(graph, "2048x1024")
    object_result = module.set_graph_output_size_pixels(graph, {"width": 512, "height": 256})

    assert text_result["width_log2"] == 11
    assert text_result["height_log2"] == 10
    assert object_result["width_log2"] == 9
    assert object_result["height_log2"] == 8
    assert graph.values["$outputsize"].value == (9, 8)


def test_resolution_to_log2_accepts_power_of_two_values() -> None:
    """Resolution conversion accepts exact powers of two."""
    module = _load_graph_output_size_module()

    assert module.resolution_to_log2(1) == 0
    assert module.resolution_to_log2("256") == 8


def test_resolution_to_log2_rejects_non_power_of_two_values() -> None:
    """Resolution conversion rejects non-power-of-two values."""
    module = _load_graph_output_size_module()

    try:
        module.resolution_to_log2(300)
    except ValueError as exc:
        assert "power of two" in str(exc)
    else:
        raise AssertionError("resolution_to_log2 accepted a non-power-of-two value")


def _load_graph_output_size_module() -> types.ModuleType:
    """Load graph output-size helpers with fake SD modules."""
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.graph.graph_output_size", GRAPH_OUTPUT_SIZE_PATH)
    for module_name in [
        "plugin",
        "plugin.graph.graph_types",
        "plugin.graph.graph_output_size",
        "sd",
        "sd.api",
        "sd.api.sdbasetypes",
        "sd.api.sdproperty",
        "sd.api.sdvalueint2",
    ]:
        sys.modules.pop(module_name, None)
    return module


def _install_fake_sd_modules() -> None:
    sd_module = types.ModuleType("sd")
    api_module = types.ModuleType("sd.api")
    base_types_module = types.ModuleType("sd.api.sdbasetypes")
    base_types_module.int2 = lambda x_value, y_value: (x_value, y_value)
    property_module = types.ModuleType("sd.api.sdproperty")
    property_module.SDPropertyCategory = types.SimpleNamespace(Input="Input")
    value_int2_module = types.ModuleType("sd.api.sdvalueint2")
    value_int2_module.SDValueInt2 = FakeSDValueInt2
    sys.modules["sd"] = sd_module
    sys.modules["sd.api"] = api_module
    sys.modules["sd.api.sdbasetypes"] = base_types_module
    sys.modules["sd.api.sdproperty"] = property_module
    sys.modules["sd.api.sdvalueint2"] = value_int2_module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path without writing bytecode."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module
