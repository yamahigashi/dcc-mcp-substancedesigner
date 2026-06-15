"""Plugin entrypoint lifecycle helpers."""

from __future__ import annotations

from .bridge.bridge_types import CommandDispatcher, JsonFallbackValue, MainThreadRunner
from .json_types import JsonScalar
from .plugin_lifecycle_types import ExceptionReporter, JsonDefault, LogSink, ServerController, ServerFactory


def log(message: str) -> None:
    """Write a namespaced plugin log line."""
    print("[SD-MCP] {}".format(message))


def json_safe(value: JsonFallbackValue) -> JsonScalar:
    """Convert otherwise unsupported JSON values into safe fallback scalars."""
    if isinstance(value, float):
        if value != value:
            return None
        if value == float("inf"):
            return 1e308
        if value == float("-inf"):
            return -1e308
    return str(value)


def log_runtime_status(
    log_sink: LogSink, pyside_path: str | None, qt_binding: str | None, invoker_is_ready: bool
) -> None:
    """Log Qt and PySide runtime readiness."""
    if pyside_path:
        log_sink("PySide path injected: {}".format(pyside_path))
    else:
        log_sink("Warning: PySide6 path not found")

    if qt_binding:
        log_sink("Qt binding: {}".format(qt_binding))
    else:
        log_sink("FATAL: No Qt binding. All MCP calls will fail.")

    if invoker_is_ready:
        log_sink("Qt invoker ready (Signal/Slot dispatch)")
    else:
        log_sink("FATAL: Qt invoker creation failed")


def start_plugin_server(
    server_factory: ServerFactory,
    handler: CommandDispatcher,
    run_on_main: MainThreadRunner,
    json_default: JsonDefault,
    log: LogSink,
    version: tuple[int, int, int],
    ports: list[int],
    pyside_path: str | None,
    qt_binding: str | None,
    invoker_is_ready: bool,
    report_exception: ExceptionReporter,
) -> ServerController | None:
    """Log host runtime status, start the bridge server, and return it."""
    version_text = ".".join(map(str, version))
    log("Initializing v{}".format(version_text))
    log_runtime_status(log, pyside_path, qt_binding, invoker_is_ready)
    try:
        server = server_factory(
            handler=handler,
            run_on_main=run_on_main,
            json_default=json_default,
            log=log,
            version=version,
            ports=ports,
        )
        server.start()
        log("Plugin v{} ready! Port: {}".format(version_text, ports))
        return server
    except Exception as exc:
        log("FATAL: Failed to start server: {}".format(exc))
        report_exception()
        return None


def stop_plugin_server(server: ServerController | None, log: LogSink) -> None:
    """Stop the bridge server when it exists."""
    log("Uninitializing")
    if server is not None:
        server.stop()
