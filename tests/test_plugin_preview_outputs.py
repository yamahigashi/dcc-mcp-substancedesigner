"""Tests for plugin-side preview output helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_OUTPUT_SELECTION_PATH = REPO_ROOT / "plugin" / "preview" / "preview_outputs.py"
PREVIEW_TEMPORARY_OUTPUT_PATH = REPO_ROOT / "plugin" / "preview" / "preview_outputs.py"
PREVIEW_TEXTURE_SAVE_PATH = REPO_ROOT / "plugin" / "preview" / "preview_outputs.py"


class FakeType:
    """Fake SD type."""

    def __init__(self, type_id: str) -> None:
        """Store a fake type identifier."""
        self.type_id = type_id

    def getId(self) -> str:
        """Return the fake type identifier."""
        return self.type_id


class FakeProperty:
    """Fake SD output property."""

    def __init__(self, property_id: str, type_id: str) -> None:
        """Store a fake property id and type id."""
        self.property_id = property_id
        self.type_id = type_id

    def getId(self) -> str:
        """Return the fake property id."""
        return self.property_id

    def getType(self) -> FakeType:
        """Return the fake property type."""
        return FakeType(self.type_id)


class FakeNode:
    """Fake preview node."""

    def __init__(self, outputs: list[FakeProperty]) -> None:
        """Store fake output properties."""
        self.outputs = outputs

    def getIdentifier(self) -> str:
        """Return the fake node identifier."""
        return "node_a"

    def getProperties(self, _category: int) -> list[FakeProperty]:
        """Return fake output properties."""
        return self.outputs

    def newPropertyConnectionFromId(
        self, output_id: str, target_node: FakeTemporaryOutputNode, target_input_id: str
    ) -> str:
        """Return a fake connection marker."""
        return "{}->{}.{}".format(output_id, target_node.getIdentifier(), target_input_id)

    def getPropertyValue(self, _prop: FakeProperty) -> FakeValue:
        """Return a fake preview value."""
        return FakeValue()


class FakeTemporaryOutputNode(FakeNode):
    """Fake temporary output node."""

    def __init__(self) -> None:
        """Initialize fake temporary output state."""
        super().__init__([FakeProperty("preview", "SDTexture")])
        self.annotations: dict[str, str] = {}
        self.position: tuple[float, float] | None = None

    def getIdentifier(self) -> str:
        """Return the fake temporary node identifier."""
        return "temporary_output"

    def setPosition(self, position: tuple[float, float]) -> None:
        """Record a fake position."""
        self.position = position

    def setAnnotationPropertyValueFromId(self, property_id: str, value: str) -> None:
        """Record an annotation value."""
        self.annotations[property_id] = value

    def getPropertyValue(self, _prop: FakeProperty) -> FakeValue:
        """Return a fake preview value."""
        return FakeValue()


class FakeGraph:
    """Fake graph for temporary output preview tests."""

    def __init__(self) -> None:
        """Initialize graph state."""
        self.temp_node = FakeTemporaryOutputNode()
        self.computed = False
        self.deleted = False

    def newNode(self, definition_id: str) -> FakeTemporaryOutputNode | None:
        """Create a fake temporary output node."""
        if definition_id != "sbs::compositing::output":
            return None
        return self.temp_node

    def compute(self) -> None:
        """Record a compute call."""
        self.computed = True

    def deleteNode(self, node: FakeTemporaryOutputNode) -> None:
        """Record temporary node deletion."""
        self.deleted = node is self.temp_node


class FakeTexture:
    """Fake saveable texture."""

    saved_path: str | None = None

    def save(self, image_path: str) -> None:
        """Record a save path."""
        FakeTexture.saved_path = image_path
        Path(image_path).write_bytes(b"fake texture")


class FakeValue:
    """Fake SDValue wrapper."""

    def get(self) -> FakeTexture:
        """Return a fake texture."""
        return FakeTexture()


def test_find_node_output_property_prefers_texture_outputs() -> None:
    """Verify preview output selection prefers texture-like properties."""
    module = _load_preview_outputs_module()
    node = FakeNode([FakeProperty("mask", "float"), FakeProperty("basecolor", "SDTexture")])

    prop = module.find_node_output_property(node)

    assert prop.getId() == "basecolor"


def test_require_texture_output_property_rejects_known_non_texture_output() -> None:
    """Verify known non-texture output properties are rejected."""
    module = _load_preview_outputs_module()
    node = FakeNode([])
    prop = FakeProperty("amount", "float")

    try:
        module.require_texture_output_property(node, prop)
    except ValueError as exc:
        assert "not a texture output" in str(exc)
    else:
        raise AssertionError("non-texture output was accepted")


def test_save_node_preview_texture_uses_wrapped_texture() -> None:
    """Verify wrapped texture values can be saved."""
    module = _load_preview_outputs_module()
    FakeTexture.saved_path = None

    module.save_node_preview_texture(FakeValue(), "/tmp/preview.png", "node_a", "basecolor")

    assert FakeTexture.saved_path == "/tmp/preview.png"


def test_export_node_output_texture_saves_to_requested_path(tmp_path: Path) -> None:
    """Verify export helper computes the graph and writes the requested node output path."""
    module = _load_preview_outputs_module()
    graph = FakeGraph()
    node = FakeNode([FakeProperty("basecolor", "SDTexture")])
    output_path = tmp_path / "basecolor.png"

    result = module.export_node_output_texture(graph, node, node.outputs[0], str(output_path))

    assert graph.computed is True
    assert output_path.read_bytes() == b"fake texture"
    assert result["node_id"] == "node_a"
    assert result["node_output_id"] == "basecolor"
    assert result["file_path"] == str(output_path)
    assert result["format"] == "png"


def test_save_node_preview_via_temporary_output_cleans_up_node() -> None:
    """Verify temporary output fallback saves and cleans up the node."""
    module = _load_preview_outputs_module()
    graph = FakeGraph()
    node = FakeNode([FakeProperty("basecolor", "SDTexture")])
    FakeTexture.saved_path = None

    module.save_node_preview_via_temporary_output(graph, node, "basecolor", "/tmp/fallback.png")

    assert FakeTexture.saved_path == "/tmp/fallback.png"
    assert graph.computed is True
    assert graph.deleted is True
    assert "usage" not in graph.temp_node.annotations
    assert graph.temp_node.annotations["usages"].items[0].value.name == "mcp_preview_node_a_basecolor"


def _load_preview_outputs_module() -> types.ModuleType:
    """Load concrete preview output helper modules as package modules."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_types",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
        "plugin.preview.preview_outputs",
    ]:
        sys.modules.pop(module_name, None)
    module = _load_module("plugin.preview.preview_outputs", PREVIEW_OUTPUT_SELECTION_PATH)
    texture = _load_module("plugin.preview.preview_outputs", PREVIEW_TEXTURE_SAVE_PATH)
    temporary = _load_module("plugin.preview.preview_outputs", PREVIEW_TEMPORARY_OUTPUT_PATH)
    module.save_node_preview_texture = texture.save_node_preview_texture
    module.save_node_preview_via_temporary_output = temporary.save_node_preview_via_temporary_output
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path under an explicit module name."""
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
