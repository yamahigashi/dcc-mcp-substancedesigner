"""Tests for plugin-side node preview render orchestration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_RENDER_PATH = REPO_ROOT / "plugin" / "preview" / "preview_render.py"


class FakeType:
    """Fake property type."""

    def __init__(self, type_id: str) -> None:
        """Store type id."""
        self.type_id = type_id

    def getId(self) -> str:
        """Return type id."""
        return self.type_id


class FakeDefinition:
    """Fake node definition."""

    def getId(self) -> str:
        """Return node definition id."""
        return "sbs::compositing::uniform"


class FakeProperty:
    """Fake property."""

    def __init__(self, property_id: str, type_id: str = "SDTexture") -> None:
        """Store property id and type."""
        self.property_id = property_id
        self.type_id = type_id

    def getId(self) -> str:
        """Return property id."""
        return self.property_id

    def getType(self) -> FakeType:
        """Return property type."""
        return FakeType(self.type_id)


class FakeTexture:
    """Fake texture with save support."""

    def __repr__(self) -> str:
        """Return a stable representation."""
        return "fake_texture"

    def save(self, image_path: str) -> None:
        """Create a fake PNG file."""
        Path(image_path).write_bytes(b"fake png")


class FakeValue:
    """Fake SDValue wrapper."""

    def get(self) -> FakeTexture:
        """Return a fake texture."""
        return FakeTexture()


class FakeNode:
    """Fake preview node."""

    def __init__(self, value: FakeValue | None = None) -> None:
        """Initialize node state."""
        self.value = value

    def getIdentifier(self) -> str:
        """Return node id."""
        return "node_a"

    def getDefinition(self) -> FakeDefinition:
        """Return node definition."""
        return FakeDefinition()

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return output or input properties."""
        if category == 0:
            return []
        return [FakeProperty("basecolor")]

    def getPropertyConnections(self, prop: FakeProperty) -> list[FakeConnection]:
        """Return no connections."""
        return []

    def getPropertyValue(self, prop: FakeProperty) -> FakeValue | None:
        """Return a fake output value."""
        return self.value

    def newPropertyConnectionFromId(
        self,
        output_id: str,
        target_node: FakeNode,
        target_input_id: str,
    ) -> str:
        """Return a fake connection marker."""
        return "{}:{}:{}".format(output_id, target_node.getIdentifier(), target_input_id)


class FakeConnection:
    """Fake preview connection."""


class FakeGraph:
    """Fake graph for preview rendering."""

    def __init__(self) -> None:
        """Initialize graph state."""
        self.computed = False
        self.compute_count = 0
        self.output_size_writes: list[tuple[str, tuple[int, int]]] = []
        self.inputs = {
            "$outputsize": (8, 8),
            "seed": 1,
        }

    def getIdentifier(self) -> str:
        """Return graph id."""
        return "graph_a"

    def getUrl(self) -> str:
        """Return graph URL."""
        return "pkg:///graph_a"

    def getPropertyFromId(self, property_id: str, category: int) -> FakeProperty | None:
        """Return no host property handle."""
        return None

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return graph input properties."""
        if category == 0:
            return [FakeProperty(property_id, "int") for property_id in self.inputs]
        return []

    def getPropertyValue(self, property_handle: FakeProperty) -> tuple[int, int]:
        """Return current output size."""
        return self.inputs[property_handle.getId()]

    def getInputPropertyValueFromId(self, property_id: str) -> tuple[int, int]:
        """Return current output size."""
        return self.inputs[property_id]

    def setInputPropertyValueFromId(self, property_id: str, value: tuple[int, int]) -> None:
        """Record output-size changes."""
        self.output_size_writes.append((property_id, value))

    def compute(self) -> None:
        """Record compute call."""
        self.computed = True
        self.compute_count += 1

    def newNode(self, definition_id: str) -> FakeNode | None:
        """Create no temporary node in this test."""
        return None

    def deleteNode(self, node: FakeNode) -> None:
        """Delete a fake node."""


def test_render_node_preview_saves_image_and_caches_payload() -> None:
    """Preview renderer saves an image and reuses cached payloads."""
    module = _load_preview_render_module()
    graph = FakeGraph()
    node = FakeNode(FakeValue())
    cache: dict[str, dict[str, module.JsonValue]] = {}

    first = module.render_node_preview(graph, node, "node_a", None, "rgba", "small", 10000, cache, None)
    second = module.render_node_preview(graph, node, "node_a", None, "rgba", "small", 10000, cache, None)

    assert Path(first["image_path"]).is_file()
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["render_ms"] == 0
    assert first["width"] == 256
    assert first["height"] == 256
    assert graph.computed is True
    assert graph.output_size_writes == []
    assert graph.compute_count == 1


def test_render_node_preview_warns_for_nearly_black_solid_preview(monkeypatch) -> None:
    """Preview payload should warn when the rendered image is effectively black and flat."""
    module = _load_preview_render_module()
    monkeypatch.setattr(
        module,
        "preview_image_stats",
        lambda image_path, qt_binding: {"mean": 1.0, "min": 1, "max": 1, "range": 0, "nonzero_ratio": 1.0},
    )
    graph = FakeGraph()
    node = FakeNode(FakeValue())

    result = module.render_node_preview(graph, node, "node_a", None, "rgba", "small", 10000, {}, None)

    assert result["preview_stats"]["mean"] == 1.0
    assert {
        "severity": "warning",
        "stage": "preview_analysis",
        "code": "near_black_solid_preview",
        "message": "Preview is nearly black and low-contrast; verify the node/output before continuing.",
    } in result["diagnostics"]


def test_render_node_preview_cache_key_includes_graph_inputs() -> None:
    """Preview cache invalidates when graph input values change."""
    module = _load_preview_render_module()
    graph = FakeGraph()
    node = FakeNode(FakeValue())
    cache: dict[str, dict[str, module.JsonValue]] = {}

    first = module.render_node_preview(graph, node, "node_a", None, "rgba", "small", 10000, cache, None)
    graph.inputs["seed"] = 2
    second = module.render_node_preview(graph, node, "node_a", None, "rgba", "small", 10000, cache, None)

    assert first["cached"] is False
    assert second["cached"] is False
    assert first["parameters_hash"] != second["parameters_hash"]
    assert len(cache) == 2
    assert graph.compute_count == 2


def test_preview_size_rejects_unknown_resolution() -> None:
    """Preview size helper rejects unknown resolution labels."""
    module = _load_preview_render_module()

    try:
        module.preview_size("huge")
    except ValueError as exc:
        assert "resolution must be one of" in str(exc)
    else:
        raise AssertionError("unknown resolution was accepted")


def _load_preview_render_module() -> types.ModuleType:
    """Load preview render modules with fake Substance Designer APIs."""
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    for module_name, path in [
        ("plugin.node.node_catalog", REPO_ROOT / "plugin" / "node" / "node_catalog.py"),
        ("plugin.preview.preview_render", REPO_ROOT / "plugin" / "preview" / "preview_render.py"),
        ("plugin.sd_serialization", REPO_ROOT / "plugin" / "sd_serialization.py"),
    ]:
        _load_module(module_name, path)
    module = _load_module("plugin.preview.preview_render", PREVIEW_RENDER_PATH)
    _remove_fake_modules()
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from disk without writing bytecode."""
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


def _install_fake_sd_modules() -> None:
    sd_module = types.ModuleType("sd")
    api_module = types.ModuleType("sd.api")
    sys.modules["sd"] = sd_module
    sys.modules["sd.api"] = api_module

    base_types = types.ModuleType("sd.api.sdbasetypes")
    base_types.float2 = lambda x_value, y_value: (x_value, y_value)
    sys.modules["sd.api.sdbasetypes"] = base_types

    property_module = types.ModuleType("sd.api.sdproperty")

    class FakeCategory:
        """Fake SD property categories."""

        Input = 0
        Output = 1

    property_module.SDPropertyCategory = FakeCategory
    sys.modules["sd.api.sdproperty"] = property_module

    value_string_module = types.ModuleType("sd.api.sdvaluestring")
    value_string_module.SDValueString = str
    sys.modules["sd.api.sdvaluestring"] = value_string_module


def _remove_fake_modules() -> None:
    """Remove fake modules installed for preview render helper loading."""
    for module_name in [
        "plugin",
        "plugin.graph.graph_types",
        "plugin.node.node_catalog",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_types",
        "plugin.preview.preview_render",
        "plugin.preview.preview_render",
        "plugin.preview.preview_render",
        "plugin.preview.preview_types",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_types",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_render",
        "plugin.preview.preview_render",
        "plugin.preview.preview_render",
        "plugin.preview.preview_types",
        "plugin.sd_serialization",
        "plugin.sd_serialization_types",
        "plugin.sd_serialization_values",
        "sd",
        "sd.api",
        "sd.api.sdbasetypes",
        "sd.api.sdproperty",
        "sd.api.sdvaluestring",
    ]:
        sys.modules.pop(module_name, None)
