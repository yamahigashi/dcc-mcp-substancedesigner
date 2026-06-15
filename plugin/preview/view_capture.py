"""3D View capture helpers for the host plugin."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import tempfile
import time
from typing import Protocol, cast

from ..graph.graph_types import GraphResource, UiManager
from ..json_types import JsonMap, JsonValue
from .preview_outputs import normalize_preview_image_size
from .preview_render import preview_size


class _Widget(Protocol):
    """Qt widget subset needed for 3D View capture."""

    def objectName(self) -> str:
        """Return the widget object name."""
        ...

    def windowTitle(self) -> str:
        """Return the widget window title."""
        ...

    def metaObject(self) -> "_MetaObject":
        """Return the Qt meta object."""
        ...

    def isVisible(self) -> bool:
        """Return whether the widget is visible."""
        ...

    def width(self) -> int:
        """Return widget width."""
        ...

    def height(self) -> int:
        """Return widget height."""
        ...

    def findChildren(self, widget_type: type) -> list["_Widget"]:
        """Return descendant widgets."""
        ...

    def grabFramebuffer(self) -> JsonValue:
        """Return an OpenGL framebuffer image when supported."""
        ...

    def grab(self) -> JsonValue:
        """Return a pixmap of the widget contents."""
        ...

    def winId(self) -> int:
        """Return native window id."""
        ...

    def window(self) -> "_Window":
        """Return the owning window."""
        ...


class _Window(Protocol):
    """Qt window subset used for screen captures."""

    def windowHandle(self) -> "_WindowHandle":
        """Return the native window handle."""
        ...


class _WindowHandle(Protocol):
    """Qt window-handle subset used for screen captures."""

    def screen(self) -> "_Screen":
        """Return the screen containing the window."""
        ...


class _Screen(Protocol):
    """Qt screen subset used for screen captures."""

    def grabWindow(self, window_id: int) -> JsonValue:
        """Grab a native window by id."""
        ...


class _Application(Protocol):
    """QApplication subset used for widget discovery."""

    @staticmethod
    def instance() -> "_Application | None":
        """Return the active application."""
        ...

    def processEvents(self) -> None:
        """Flush pending UI events."""
        ...

    def topLevelWidgets(self) -> list[_Widget]:
        """Return top-level widgets."""
        ...

    def allWidgets(self) -> list[_Widget]:
        """Return every application widget."""
        ...


class _QtWidgetsModule(Protocol):
    """QtWidgets subset used for widget discovery."""

    QApplication: type
    QWidget: type


class _MetaObject(Protocol):
    """Qt meta-object subset used for widget class names."""

    def className(self) -> str:
        """Return Qt class name."""
        ...


class _Pixmap(Protocol):
    """Qt pixmap subset used for image saving."""

    def save(self, image_path: str, image_format: str) -> bool:
        """Save the pixmap to disk."""
        ...


def capture_graph_3d_view(
    graph: GraphResource,
    ui_manager: UiManager,
    graph_identifier: str | None,
    resolution: str,
    timeout_ms: int,
    qt_binding: str | None,
    width: int | None = None,
    height: int | None = None,
) -> JsonMap:
    """Open a graph when requested and save the current 3D View widget as PNG."""
    if int(timeout_ms) <= 0:
        raise ValueError("timeout_ms must be > 0")
    target_width, target_height = preview_dimensions(resolution, width, height)
    started = time.time()
    opened_graph = False
    if graph_identifier:
        ui_manager.openResourceInEditor(graph)
        opened_graph = True

    widgets_module = qt_widgets_module(qt_binding)
    app = qt_application(widgets_module)
    app.processEvents()
    candidates = find_3d_view_widget_candidates(app, widgets_module.QWidget)
    image_path = graph_preview_image_path(
        {
            "graph_identifier": graph.getIdentifier(),
            "resolution": resolution,
            "width": target_width,
            "height": target_height,
            "captured_at_ms": int(started * 1000),
        }
    )
    capture_error = save_first_available_widget(candidates, image_path)
    if not os.path.exists(image_path):
        if capture_error:
            raise RuntimeError("3D View preview PNG was not created: {} ({})".format(image_path, capture_error))
        raise RuntimeError("3D View preview PNG was not created: {}".format(image_path))
    normalize_preview_image_size(image_path, target_width, target_height, qt_binding)

    captured_ms = int((time.time() - started) * 1000)
    if captured_ms > int(timeout_ms):
        raise RuntimeError("3D View preview capture exceeded timeout_ms: {}ms > {}ms".format(captured_ms, timeout_ms))

    graph_id = graph.getIdentifier()
    return {
        "preview_type": "graph_3d_view",
        "image_path": image_path,
        "width": target_width,
        "height": target_height,
        "graph_id": graph_id,
        "graph_identifier": graph_id,
        "resolution": resolution,
        "captured_ms": captured_ms,
        "requires_ui": True,
        "opened_graph": opened_graph,
    }


def preview_dimensions(resolution: str, width: int | None, height: int | None) -> tuple[int, int]:
    """Return requested graph preview dimensions."""
    size = preview_size(resolution)
    resolved_width = positive_dimension(width, "width") if width is not None else size
    resolved_height = positive_dimension(height, "height") if height is not None else size
    return resolved_width, resolved_height


def positive_dimension(value: int, name: str) -> int:
    """Validate and return a positive image dimension."""
    dimension = int(value)
    if dimension <= 0:
        raise ValueError("{} must be > 0".format(name))
    return dimension


def qt_widgets_module(qt_binding: str | None) -> _QtWidgetsModule:
    """Return the QtWidgets module for the detected Qt binding."""
    if not qt_binding:
        raise RuntimeError("Qt binding unavailable; cannot capture 3D View.")
    widgets_module_name = qt_binding.rsplit(".", 1)[0] + ".QtWidgets"
    return cast(_QtWidgetsModule, importlib.import_module(widgets_module_name))


def qt_application(widgets_module: _QtWidgetsModule) -> _Application:
    """Return the active QApplication for the detected Qt binding."""
    app = widgets_module.QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication unavailable; cannot capture 3D View.")
    return cast(_Application, app)


def find_3d_view_widget(app: _Application, widget_type: type) -> _Widget:
    """Find the most likely visible 3D View widget."""
    candidates = find_3d_view_widget_candidates(app, widget_type)
    if not candidates:
        raise RuntimeError("Visible 3D View widget was not found. Open the 3D View and retry get_preview.")
    return candidates[0]


def find_3d_view_widget_candidates(app: _Application, widget_type: type) -> list[_Widget]:
    """Return likely 3D View capture candidates ordered from best to worst."""
    candidates = [
        (score_3d_view_widget(widget), widget_area(widget), widget) for widget in collect_widgets(app, widget_type)
    ]
    candidates = [(score, area, widget) for score, area, widget in candidates if score > 0]
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [widget for _score, _area, widget in candidates]


def collect_widgets(app: _Application, widget_type: type) -> list[_Widget]:
    """Return visible widgets from QApplication, including nested dock contents."""
    widgets: list[_Widget] = []
    seen: set[int] = set()
    append_unique_widgets(widgets, seen, app.allWidgets())
    top_level = app.topLevelWidgets()
    append_unique_widgets(widgets, seen, top_level)
    for widget in top_level:
        try:
            append_unique_widgets(widgets, seen, widget.findChildren(widget_type))
        except Exception:
            pass
    return [widget for widget in widgets if is_visible_capture_widget(widget)]


def append_unique_widgets(widgets: list[_Widget], seen: set[int], candidates: list[_Widget]) -> None:
    """Append widgets while preserving order and avoiding duplicates."""
    for candidate in candidates:
        marker = id(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        widgets.append(candidate)


def is_visible_capture_widget(widget: _Widget) -> bool:
    """Return whether a widget can be captured."""
    try:
        return is_qt_object_valid(widget) and widget.isVisible() and widget.width() > 0 and widget.height() > 0
    except Exception:
        return False


def score_3d_view_widget(widget: _Widget) -> int:
    """Score how likely a widget is to be the 3D View capture target."""
    normalized = normalize_widget_text(widget_metadata_text(widget))
    area = widget_area(widget)
    if any(
        token in normalized
        for token in (
            "toolbar",
            "menubar",
            "statusbar",
            "button",
            "combobox",
            "lineedit",
            "splitter",
            "tabbar",
            "scrollbar",
        )
    ):
        return 0
    score = 0
    if any(token in normalized for token in ("opengl", "glwidget", "qopengl", "qquick", "viewport", "render")):
        score += 160
    if "3d" in normalized and any(token in normalized for token in ("view", "viewer", "viewport")):
        score += 100
    if "3d" in normalized and "dock" in normalized:
        score += 60
    if any(token in normalized for token in ("sd3d", "3dview", "3dviewer", "3dviewport")):
        score += 90
    if area >= 160 * 120:
        score += 5
    return score


def save_first_available_widget(widgets: list[_Widget], image_path: str) -> str:
    """Try candidate widgets until one can be grabbed and saved."""
    last_error = ""
    for widget in widgets:
        try:
            if not is_visible_capture_widget(widget):
                continue
            saved, error = save_widget_capture(widget, image_path)
            if saved:
                return ""
            last_error = "{}: {}".format(widget_metadata_text(widget), error)
        except Exception as exc:
            last_error = "{}: {}".format(widget_metadata_text(widget), exc)
    return last_error or "no capturable 3D View candidate"


def save_widget_capture(widget: _Widget, image_path: str) -> tuple[bool, str]:
    """Save one widget using capture methods that work with OpenGL-backed views."""
    errors: list[str] = []
    for label, method in (
        ("framebuffer", save_widget_framebuffer),
        ("screen", save_widget_screen_grab),
        ("widget", save_widget_grab),
    ):
        try:
            if method(widget, image_path):
                return True, ""
            errors.append("{} returned false".format(label))
        except Exception as exc:
            errors.append("{} failed: {}".format(label, exc))
    return False, "; ".join(errors)


def save_widget_framebuffer(widget: _Widget, image_path: str) -> bool:
    """Save an OpenGL/QQuick framebuffer when the widget supports it."""
    image = widget.grabFramebuffer()
    return save_qt_image(image, image_path)


def save_widget_screen_grab(widget: _Widget, image_path: str) -> bool:
    """Save a compositor-level screen grab for widgets whose paint engine cannot be grabbed directly."""
    screen = widget.window().windowHandle().screen()
    pixmap = screen.grabWindow(int(widget.winId()))
    return save_qt_image(pixmap, image_path)


def save_widget_grab(widget: _Widget, image_path: str) -> bool:
    """Save a normal QWidget grab."""
    return save_qt_image(widget.grab(), image_path)


def save_qt_image(image: JsonValue, image_path: str) -> bool:
    """Save a Qt pixmap/image-like object to PNG."""
    output_dir = os.path.dirname(image_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return cast(_Pixmap, image).save(image_path, "PNG") is not False and os.path.exists(image_path)


def is_qt_object_valid(widget: _Widget) -> bool:
    """Return whether a PySide wrapper still points to a live C++ object."""
    module_name = type(widget).__module__.split(".", 1)[0]
    if module_name not in {"PySide2", "PySide6"}:
        return True
    shiboken_module_name = "shiboken6" if module_name == "PySide6" else "shiboken2"
    try:
        shiboken = importlib.import_module(shiboken_module_name)
        return bool(shiboken.isValid(widget))
    except Exception:
        return True


def widget_metadata_text(widget: _Widget) -> str:
    """Return searchable widget metadata."""
    return " ".join(
        [
            safe_widget_text(widget, "objectName"),
            safe_widget_text(widget, "windowTitle"),
            safe_meta_class_name(widget),
        ]
    )


def normalize_widget_text(text: str) -> str:
    """Normalize widget metadata for loose matching."""
    return text.lower().replace("_", "").replace("-", "").replace(" ", "")


def widget_area(widget: _Widget) -> int:
    """Return positive widget area."""
    try:
        return max(0, widget.width()) * max(0, widget.height())
    except Exception:
        return 0


def safe_widget_text(widget: _Widget, method_name: str) -> str:
    """Read a widget text attribute best-effort."""
    try:
        method = getattr(widget, method_name)
        value = method()
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def safe_meta_class_name(widget: _Widget) -> str:
    """Read a widget Qt class name best-effort."""
    try:
        meta = widget.metaObject()
        class_name = meta.className()
        return class_name if isinstance(class_name, str) else ""
    except Exception:
        return ""


def graph_preview_image_path(parts: dict[str, JsonValue]) -> str:
    """Return a PNG path for one graph 3D View capture."""
    output_dir = os.path.join(tempfile.gettempdir(), "dcc_mcp_substancedesigner", "previews")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    serialized = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    cache_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return os.path.join(output_dir, "{}.png".format(cache_key))
