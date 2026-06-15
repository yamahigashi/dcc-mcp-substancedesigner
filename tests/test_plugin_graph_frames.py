"""Tests for plugin-side graph frame helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_FRAMES_PATH = REPO_ROOT / "plugin" / "graph" / "graph_frames.py"


class FakePosition:
    """Fake graph editor position."""

    def __init__(self, x_value: float, y_value: float) -> None:
        """Store coordinates."""
        self.x = x_value
        self.y = y_value


class FakeNode:
    """Fake graph node."""

    def __init__(self, node_id: str, x_value: float, y_value: float) -> None:
        """Store node identity and position."""
        self.node_id = node_id
        self.position = FakePosition(x_value, y_value)

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        return self.node_id

    def getPosition(self) -> FakePosition:
        """Return the node position."""
        return self.position


class FakeGraph:
    """Fake graph that owns frames."""


class FakeFrame:
    """Fake graph frame."""

    created: list[FakeFrame] = []

    def __init__(self, graph: FakeGraph) -> None:
        """Initialize frame state."""
        self.graph = graph
        self.position: tuple[float, float] | None = None
        self.size: tuple[float, float] | None = None
        self.title = ""
        self.description = ""
        self.color: tuple[float, float, float, float] | None = None
        self.created.append(self)

    @staticmethod
    def sNew(graph: FakeGraph) -> FakeFrame:
        """Create a fake frame."""
        return FakeFrame(graph)

    def setPosition(self, position: tuple[float, float]) -> None:
        """Record frame position."""
        self.position = position

    def setSize(self, size: tuple[float, float]) -> None:
        """Record frame size."""
        self.size = size

    def setTitle(self, title: str) -> None:
        """Record frame title."""
        self.title = title

    def setDescription(self, description: str) -> None:
        """Record frame description."""
        self.description = description

    def setColor(self, color: tuple[float, float, float, float]) -> None:
        """Record frame color."""
        self.color = color


def test_create_frame_wraps_nodes_with_padding() -> None:
    """Verify frames are sized from target node bounds."""
    module = _load_graph_frames_module()
    graph = FakeGraph()
    nodes = [FakeNode("left", 100, 200), FakeNode("right", 500, 420)]

    result = module.create_frame(graph, nodes, "USER EDIT Splines", "Spline controls", None, None, 80, None)

    frame = FakeFrame.created[-1]
    assert frame.graph is graph
    assert frame.title == "USER EDIT Splines"
    assert frame.description == "Spline controls"
    assert frame.position == (20.0, 120.0)
    assert frame.size == (560.0, 380.0)
    assert result["node_ids"] == ["left", "right"]
    assert result["grouped"] is True


def test_create_frame_accepts_explicit_bounds_and_color() -> None:
    """Verify explicit frame bounds and color are honored."""
    module = _load_graph_frames_module()

    result = module.create_frame(
        FakeGraph(),
        [],
        "Reference",
        "",
        [10, 20],
        [300, 200],
        80,
        [0.1, 0.2, 0.3, 0.4],
    )

    frame = FakeFrame.created[-1]
    assert frame.position == (10.0, 20.0)
    assert frame.size == (300.0, 200.0)
    assert frame.color == (0.1, 0.2, 0.3, 0.4)
    assert result["grouped"] is False


def test_create_frame_accepts_mapping_bounds_and_color_aliases() -> None:
    """Frame helper accepts UI-style vector and color objects."""
    module = _load_graph_frames_module()

    result = module.create_frame(
        FakeGraph(),
        [],
        "Reference",
        "",
        {"x": 10, "y": 20},
        {"width": 300, "height": 200},
        80,
        {"red": 0.1, "green": 0.2, "blue": 0.3},
    )

    frame = FakeFrame.created[-1]
    assert frame.position == (10.0, 20.0)
    assert frame.size == (300.0, 200.0)
    assert frame.color == (0.1, 0.2, 0.3, 1.0)
    assert result["color"] == [0.1, 0.2, 0.3, 1.0]


def _load_graph_frames_module() -> types.ModuleType:
    """Load graph frame helpers with fake Substance modules."""
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    try:
        return _load_module("plugin.graph.graph_frames", GRAPH_FRAMES_PATH)
    finally:
        _remove_fake_modules()


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


def _install_fake_sd_modules() -> None:
    """Install fake Substance modules required by graph frame helpers."""
    sd_module = types.ModuleType("sd")
    api_module = types.ModuleType("sd.api")
    sys.modules["sd"] = sd_module
    sys.modules["sd.api"] = api_module

    base_types = types.ModuleType("sd.api.sdbasetypes")
    base_types.float2 = lambda x_value, y_value: (x_value, y_value)
    base_types.ColorRGBA = lambda r_value, g_value, b_value, a_value: (r_value, g_value, b_value, a_value)
    sys.modules["sd.api.sdbasetypes"] = base_types

    property_module = types.ModuleType("sd.api.sdproperty")

    class FakeCategory:
        """Fake SD property categories."""

        Input = 0
        Output = 1
        Annotation = 2

    property_module.SDPropertyCategory = FakeCategory
    sys.modules["sd.api.sdproperty"] = property_module

    frame_module = types.ModuleType("sd.api.sdgraphobjectframe")
    frame_module.SDGraphObjectFrame = FakeFrame
    sys.modules["sd.api.sdgraphobjectframe"] = frame_module


def _remove_fake_modules() -> None:
    """Remove fake modules installed for graph frame helper loading."""
    for module_name in [
        "plugin",
        "plugin.graph.graph_frames",
        "plugin.node.node_queries",
        "plugin.node.node_types",
        "sd",
        "sd.api",
        "sd.api.sdbasetypes",
        "sd.api.sdproperty",
        "sd.api.sdgraphobjectframe",
    ]:
        sys.modules.pop(module_name, None)
