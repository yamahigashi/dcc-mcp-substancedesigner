"""Tests for plugin-side preview image helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_IMAGE_RESIZE_PATH = REPO_ROOT / "plugin" / "preview" / "preview_outputs.py"


class FakeQt:
    """Fake Qt namespace constants for image scaling."""

    IgnoreAspectRatio = 1
    SmoothTransformation = 2


class FakeImage:
    """Fake QImage implementation for resize tests."""

    saved_path: str | None = None
    saved_format: str | None = None

    def __init__(self, image_path: str, width: int = 16, height: int = 16, null: bool = False) -> None:
        """Create a fake image with deterministic dimensions."""
        self.image_path = image_path
        self._width = width
        self._height = height
        self._null = null

    def isNull(self) -> bool:
        """Return whether this fake image is invalid."""
        return self._null

    def width(self) -> int:
        """Return the fake image width."""
        return self._width

    def height(self) -> int:
        """Return the fake image height."""
        return self._height

    def scaled(self, width: int, height: int, aspect_mode: int, transform_mode: int) -> FakeImage:
        """Return a resized fake image."""
        assert aspect_mode == FakeQt.IgnoreAspectRatio
        assert transform_mode == FakeQt.SmoothTransformation
        return FakeImage(self.image_path, width, height)

    def save(self, image_path: str, image_format: str) -> bool:
        """Record the save request."""
        FakeImage.saved_path = image_path
        FakeImage.saved_format = image_format
        return True


def test_normalize_preview_image_size_uses_matching_qt_modules() -> None:
    module = _load_preview_images_module()
    qtcore = ModuleType("PySide6.QtCore")
    qtcore.Qt = FakeQt
    qtgui = ModuleType("PySide6.QtGui")
    qtgui.QImage = FakeImage
    previous_core = sys.modules.get("PySide6.QtCore")
    previous_gui = sys.modules.get("PySide6.QtGui")
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    try:
        module.normalize_preview_image_size("/tmp/preview.png", 32, 64, "PySide6.QtCore")
    finally:
        _restore_module("PySide6.QtCore", previous_core)
        _restore_module("PySide6.QtGui", previous_gui)

    assert FakeImage.saved_path == "/tmp/preview.png"
    assert FakeImage.saved_format == "PNG"


def _load_preview_images_module() -> types.ModuleType:
    """Load concrete preview image helper modules."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.preview.preview_outputs",
    ]:
        sys.modules.pop(module_name, None)
    return _load_module("plugin.preview.preview_outputs", PREVIEW_IMAGE_RESIZE_PATH)


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


def _restore_module(name: str, module: ModuleType | None) -> None:
    """Restore or remove a sys.modules entry."""
    if module is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = module
