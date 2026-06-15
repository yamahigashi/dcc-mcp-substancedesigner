"""Host-side command dispatcher for dcc-mcp-substancedesigner.

The adapter talks to the Substance Designer plugin over a local TCP bridge.
This module owns the bridge command implementation; plugin lifecycle wiring
stays in ``plugin.__init__``.
"""

from __future__ import annotations

from typing import cast

import sd as _sd

from ..json_types import JsonMap, JsonValue
from ..library.library_nodes import preload_standard_library_packages
from ..python_execution.execution import execute_python_code
from ..python_execution.python_execution_types import SDModule
from .command_catalog import PLUGIN_COMMANDS
from .command_connection_mixin import DirectConnectCommandMixin, DisconnectCommandMixin
from .command_misc_mixin import CommandParameterMixin, CommandUtilityMixin
from .command_protocols import CommandMethod
from .node_command_creation_mixin import NodeCreationCommandMixin
from .node_command_editing_mixin import NodeEditingCommandMixin
from .node_command_nested_mixin import NodeNestedGraphCommandMixin
from .node_command_query_mixin import NodeInspectionCommandMixin, NodeLibraryCommandMixin, NodePreviewCommandMixin
from .scene_command_query_mixin import (
    SceneDiagnosticCommandMixin,
    SceneQueryCommandMixin,
)
from .scene_lifecycle_mixin import SceneLifecycleCommandMixin

sd = cast(SDModule, _sd)


class CommandHandler(
    SceneQueryCommandMixin,
    SceneLifecycleCommandMixin,
    SceneDiagnosticCommandMixin,
    NodeCreationCommandMixin,
    NodeEditingCommandMixin,
    NodeInspectionCommandMixin,
    NodePreviewCommandMixin,
    NodeNestedGraphCommandMixin,
    NodeLibraryCommandMixin,
    DirectConnectCommandMixin,
    DisconnectCommandMixin,
    CommandParameterMixin,
    CommandUtilityMixin,
):
    """Host-side command dispatcher for the raw bridge server."""

    def __init__(self) -> None:
        """Build handler and cache state for one plugin bridge server."""
        self.HANDLERS: dict[str, CommandMethod] = {
            command_name: getattr(self, command_name) for command_name in PLUGIN_COMMANDS
        }
        # Library node URL cache (populated lazily, session-lifetime)
        self._lib_url_cache: dict[str, str] = {}  # lower-case identifier -> url string
        self._preview_cache: dict[str, JsonMap] = {}  # cache key -> preview payload
        self._standard_library_preload_results = self._preload_standard_libraries()

    def dispatch(self, cmd_type: str, params: JsonMap) -> JsonValue:
        """Dispatch a validated command payload."""
        handler = self.HANDLERS.get(cmd_type)
        if not handler:
            raise ValueError("Unknown command: '{}'. Available: {}".format(cmd_type, sorted(self.HANDLERS.keys())))
        return handler(**params)

    def execute_python(self, code: str, strict_json: bool = False) -> JsonMap:
        """Execute arbitrary Python on the SD main thread."""
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code must be a non-empty string")
        return execute_python_code(sd, code, strict_json)

    def _preload_standard_libraries(self) -> list[JsonValue]:
        """Best-effort load standard library packages during bridge startup."""
        try:
            return preload_standard_library_packages(self._pkg_mgr())
        except Exception as exc:
            return [{"loaded": False, "error": str(exc)}]
