"""Qt binding and main-thread dispatch helpers for Substance Designer host calls."""

from __future__ import annotations

import importlib
import os
import queue
import sys
import threading
from collections.abc import Callable
from typing import cast

from ..bridge.bridge_protocol import DEFAULT_COMMAND_TIMEOUT
from ..plugin_lifecycle import log
from .host_types import P, QtCallback, QtCoreModule, ScheduledInvoker, T


def inject_sd_pyside_path() -> str | None:
    """Locate and add Substance Designer's bundled PySide path to sys.path."""
    candidates: list[str] = []
    try:
        psutil = importlib.import_module("psutil")

        for proc in psutil.process_iter(["name", "exe"]):
            name = (proc.info.get("name") or "").lower()
            if "substance" in name and "designer" in name:
                exe = proc.info.get("exe") or ""
                if exe:
                    candidates.append(os.path.dirname(exe))
    except Exception:
        pass

    try:
        exe_dir = os.path.dirname(sys.executable)
        for _ in range(4):
            site_pkg = os.path.join(exe_dir, "Lib", "site-packages")
            if os.path.isdir(os.path.join(site_pkg, "PySide6")):
                candidates.append(exe_dir)
                break
            exe_dir = os.path.dirname(exe_dir)
    except Exception:
        pass

    try:
        for drive in ("C:", "D:", "E:", "F:"):
            for base in (
                drive + "\\Program Files\\Adobe",
                drive + "\\Program Files (x86)\\Adobe",
                drive + "\\Create\\Build\\DCC\\SubstanceDesigner",
            ):
                if not os.path.isdir(base):
                    continue
                for item in os.listdir(base):
                    if "substance" in item.lower() and "designer" in item.lower():
                        candidates.append(os.path.join(base, item))
    except Exception:
        pass

    for sd_root in candidates:
        site_pkg = os.path.join(sd_root, "plugins", "pythonsdk", "Lib", "site-packages")
        if os.path.isdir(os.path.join(site_pkg, "PySide6")):
            if site_pkg not in sys.path:
                sys.path.insert(0, site_pkg)
            return site_pkg
    return None


def import_qtcore(binding: str) -> QtCoreModule:
    """Import a QtCore module and expose the subset used by this plugin."""
    return cast(QtCoreModule, importlib.import_module(binding))


def detect_qt_binding() -> tuple[str | None, str | None]:
    """Inject the PySide SDK path and return the first usable QtCore binding."""
    pyside_path = inject_sd_pyside_path()
    for qt_binding in ("PySide6.QtCore", "PySide2.QtCore"):
        try:
            import_qtcore(qt_binding)
            return pyside_path, qt_binding
        except Exception:
            pass
    return pyside_path, None


PYSIDE_PATH, QT_BINDING_USED = detect_qt_binding()


class _Invoker:
    """Lazy Qt signal invoker for main-thread command dispatch."""

    _instance: ScheduledInvoker | None = None

    @classmethod
    def instance(cls) -> ScheduledInvoker | None:
        """Return the singleton Qt invoker, creating it when possible."""
        if cls._instance is None:
            cls._instance = cls._build()
        return cls._instance

    @staticmethod
    def _build() -> ScheduledInvoker | None:
        """Build a Qt invoker that executes queued callbacks on the main thread."""
        if not QT_BINDING_USED:
            return None
        try:
            qtcore = import_qtcore(QT_BINDING_USED)

            class Invoker(qtcore.QObject):  # ty: ignore[unsupported-base]
                invoke_signal = qtcore.Signal()

                def __init__(self) -> None:
                    super().__init__()
                    self._queue: queue.Queue[QtCallback] = queue.Queue()
                    self.invoke_signal.connect(self._execute, qtcore.Qt.QueuedConnection)

                def schedule(self, callback: QtCallback) -> None:
                    """Schedule a callback for Qt main-thread execution."""
                    self._queue.put(callback)
                    self.invoke_signal.emit()

                def _execute(self) -> None:
                    """Execute one queued callback if a callback is waiting."""
                    try:
                        callback = self._queue.get_nowait()
                        callback()
                    except queue.Empty:
                        pass
                    except BaseException as exc:
                        log("Invoker._execute error: {}".format(exc))

            return Invoker()
        except Exception as exc:
            log("Warning: _Invoker build failed: {}".format(exc))
            return None


class MainThreadDispatcher:
    """Dispatcher that runs host API work on the Substance Designer main thread."""

    def dispatch(self, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> tuple[T | None, BaseException | None]:
        """Run a callable on the main thread and return either its result or exception."""
        if threading.current_thread() is threading.main_thread():
            try:
                return fn(*args, **kwargs), None
            except BaseException as exc:
                return None, exc

        invoker = _Invoker.instance()
        if invoker is None:
            hint = " injected: {}".format(PYSIDE_PATH) if PYSIDE_PATH else " (pythonsdk not found)"
            return None, RuntimeError("Qt invoker unavailable - cannot dispatch to main thread." + hint)

        result: T | None = None
        exception: BaseException | None = None
        done = threading.Event()

        def _call() -> None:
            nonlocal result, exception
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                exception = exc
            finally:
                done.set()

        invoker.schedule(_call)

        if not done.wait(timeout=DEFAULT_COMMAND_TIMEOUT):
            return None, TimeoutError("Main thread dispatch timed out after {}s".format(DEFAULT_COMMAND_TIMEOUT))

        return result, exception


_DISPATCHER = MainThreadDispatcher()


def run_on_main(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Run a callable through the shared main-thread dispatcher."""
    result, exception = _DISPATCHER.dispatch(fn, *args, **kwargs)
    if exception is not None:
        raise exception
    return cast(T, result)


def invoker_ready() -> bool:
    """Return whether the Qt main-thread invoker can be created."""
    return _Invoker.instance() is not None
