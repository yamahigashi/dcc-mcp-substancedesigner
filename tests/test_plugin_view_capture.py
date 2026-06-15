"""Tests for plugin-side 3D View capture helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_CAPTURE_PATH = REPO_ROOT / "plugin" / "preview" / "view_capture.py"


class FakeMeta:
    """Fake Qt meta object."""

    def __init__(self, class_name: str) -> None:
        """Store class name."""
        self.class_name = class_name

    def className(self) -> str:
        """Return class name."""
        return self.class_name


class FakePixmap:
    """Fake pixmap that can save a PNG."""

    def __init__(self, payload: bytes = b"fake png") -> None:
        """Store payload."""
        self.payload = payload

    def save(self, image_path: str, image_format: str) -> bool:
        """Save a fake image file."""
        assert image_format == "PNG"
        Path(image_path).write_bytes(self.payload)
        return True


class FakeWidget:
    """Fake Qt widget."""

    def __init__(
        self,
        object_name: str,
        window_title: str,
        class_name: str,
        width: int,
        height: int,
        children: list["FakeWidget"] | None = None,
        grab_error: Exception | None = None,
        framebuffer: FakePixmap | None = None,
    ) -> None:
        """Initialize widget metadata."""
        self._object_name = object_name
        self._window_title = window_title
        self._class_name = class_name
        self._width = width
        self._height = height
        self._children = children or []
        self._grab_error = grab_error
        self._framebuffer = framebuffer

    def objectName(self) -> str:
        """Return object name."""
        return self._object_name

    def windowTitle(self) -> str:
        """Return window title."""
        return self._window_title

    def metaObject(self) -> FakeMeta:
        """Return fake metadata."""
        return FakeMeta(self._class_name)

    def isVisible(self) -> bool:
        """Return visible state."""
        return True

    def width(self) -> int:
        """Return width."""
        return self._width

    def height(self) -> int:
        """Return height."""
        return self._height

    def findChildren(self, widget_type: type) -> list["FakeWidget"]:
        """Return child widgets."""
        return self._children

    def grab(self) -> FakePixmap:
        """Return a fake pixmap."""
        if self._grab_error is not None:
            raise self._grab_error
        return FakePixmap()

    def grabFramebuffer(self) -> FakePixmap:
        """Return a fake framebuffer."""
        if self._framebuffer is None:
            raise AttributeError("grabFramebuffer")
        return self._framebuffer

    def winId(self) -> int:
        """Return a fake native id."""
        return 1

    def window(self) -> "FakeWidget":
        """Return self as the owning window."""
        return self

    def windowHandle(self) -> "FakeWidget":
        """Return self as the native handle."""
        return self

    def screen(self) -> "FakeWidget":
        """Return self as the screen."""
        return self

    def grabWindow(self, window_id: int) -> FakePixmap:
        """Return a fake screen grab."""
        assert window_id == 1
        return FakePixmap(b"screen png")


class FakeApplication:
    """Fake QApplication."""

    def __init__(self, widgets: list[FakeWidget]) -> None:
        """Store widgets."""
        self.widgets = widgets
        self.processed = False

    def processEvents(self) -> None:
        """Record event processing."""
        self.processed = True

    def topLevelWidgets(self) -> list[FakeWidget]:
        """Return top-level widgets."""
        return self.widgets

    def allWidgets(self) -> list[FakeWidget]:
        """Return every widget."""
        found: list[FakeWidget] = []
        for widget in self.widgets:
            found.append(widget)
            found.extend(widget.findChildren(FakeWidget))
        return found


class FakeQtWidgets:
    """Fake QtWidgets module."""

    QApplication = FakeApplication
    QWidget = FakeWidget


class FakeGraph:
    """Fake graph resource."""

    def getIdentifier(self) -> str:
        """Return graph id."""
        return "GraphA"


class FakeUiManager:
    """Fake UI manager."""

    def __init__(self) -> None:
        """Initialize state."""
        self.opened = []

    def openResourceInEditor(self, graph: FakeGraph) -> None:
        """Record graph opening."""
        self.opened.append(graph.getIdentifier())


def test_capture_graph_3d_view_finds_widget_and_saves_png(monkeypatch) -> None:
    """3D View capture opens the graph and saves the visible 3D View widget."""
    module = _load_view_capture_module()
    view = FakeWidget("Designer3DView", "", "SD3DViewport", 800, 600)
    app = FakeApplication([FakeWidget("MainWindow", "Designer", "QMainWindow", 1200, 900, [view])])
    ui_manager = FakeUiManager()
    monkeypatch.setattr(module, "qt_widgets_module", lambda qt_binding: FakeQtWidgets)
    monkeypatch.setattr(module, "qt_application", lambda widgets_module: app)
    monkeypatch.setattr(module, "normalize_preview_image_size", lambda image_path, width, height, qt_binding: None)

    result = module.capture_graph_3d_view(FakeGraph(), ui_manager, "GraphA", "small", 10000, "PySide6.QtCore")

    assert Path(result["image_path"]).is_file()
    assert result["preview_type"] == "graph_3d_view"
    assert result["width"] == 256
    assert result["height"] == 256
    assert result["opened_graph"] is True
    assert app.processed is True
    assert ui_manager.opened == ["GraphA"]


def test_preview_dimensions_accepts_custom_graph_capture_size() -> None:
    """Graph preview dimensions may override the resolution preset."""
    module = _load_view_capture_module()

    assert module.preview_dimensions("medium", 640, 360) == (640, 360)


def test_find_3d_view_widget_scans_all_qapplication_widgets() -> None:
    """Widget discovery can find 3D View widgets outside top-level type matching."""
    module = _load_view_capture_module()
    view = FakeWidget("viewer", "", "QOpenGLWidget3DViewport", 640, 480)
    app = FakeApplication([FakeWidget("MainWindow", "Designer", "QMainWindow", 1200, 900, [view])])

    assert module.find_3d_view_widget(app, FakeWidget) is view


def test_capture_graph_3d_view_skips_toolbar_and_failed_grab(monkeypatch) -> None:
    """3D View capture skips toolbar/stale candidates and retries a later viewport."""
    module = _load_view_capture_module()
    toolbar = FakeWidget("3D View Toolbar", "", "QToolBar", 800, 40)
    stale = FakeWidget("3D View", "", "QOpenGLWidget", 800, 600, grab_error=RuntimeError("already deleted"))
    view = FakeWidget("3D View", "", "QOpenGLWidget", 640, 480)
    app = FakeApplication([FakeWidget("MainWindow", "Designer", "QMainWindow", 1200, 900, [toolbar, stale, view])])
    ui_manager = FakeUiManager()
    monkeypatch.setattr(module, "qt_widgets_module", lambda qt_binding: FakeQtWidgets)
    monkeypatch.setattr(module, "qt_application", lambda widgets_module: app)
    monkeypatch.setattr(module, "normalize_preview_image_size", lambda image_path, width, height, qt_binding: None)

    result = module.capture_graph_3d_view(FakeGraph(), ui_manager, None, "small", 10000, "PySide6.QtCore")

    assert Path(result["image_path"]).is_file()
    assert module.score_3d_view_widget(toolbar) == 0


def test_save_widget_capture_prefers_framebuffer_for_opengl_view() -> None:
    """OpenGL widgets use framebuffer capture before normal widget grabs."""
    module = _load_view_capture_module()
    image_path = str(Path.cwd() / ".pytest_cache" / "framebuffer_preview.png")
    widget = FakeWidget("3D View", "", "QOpenGLWidget", 640, 480, framebuffer=FakePixmap(b"framebuffer png"))

    saved, error = module.save_widget_capture(widget, image_path)

    assert saved is True
    assert error == ""
    assert Path(image_path).read_bytes() == b"framebuffer png"


def _load_view_capture_module() -> types.ModuleType:
    """Load concrete view capture helper modules as a package."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    preview_package = types.ModuleType("plugin.preview")
    preview_package.__path__ = [str(REPO_ROOT / "plugin" / "preview")]  # type: ignore[attr-defined]
    sys.modules.setdefault("plugin", package)
    sys.modules.setdefault("plugin.preview", preview_package)
    spec = importlib.util.spec_from_file_location("plugin.preview.view_capture", VIEW_CAPTURE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["plugin.preview.view_capture"] = module
    spec.loader.exec_module(module)
    return module
