"""Substance Designer command facade used by skills and tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dcc_mcp_substancedesigner.__version__ import __version__
from dcc_mcp_substancedesigner.authoring_reference import (
    SDF_FUNCTION_WORKFLOW_URI,
    load_function_contract_registry,
    node_definitions,
    node_definitions_by_id,
    public_tool_action_id,
    public_tool_action_ids,
    reference_next_tools,
    search_node_references,
    tool_hint,
)
from dcc_mcp_substancedesigner.bridge import (
    DEFAULT_SD_BRIDGE_PORT,
    SubstanceDesignerBridgeClient,
    SubstanceDesignerBridgeError,
)
from dcc_mcp_substancedesigner.graph_analysis import graph_outputs, summarize_graph, trace_output
from dcc_mcp_substancedesigner.graph_capabilities import (
    authoring_capabilities,
    authoring_plan,
    normalize_graph_change_parameters,
    normalize_graph_ref,
    resolve_graph_context,
    validate_graph_change,
)
from dcc_mcp_substancedesigner.graph_change_types import (
    GraphChangeConnection,
    GraphChangeNode,
    GraphChangeParameterItems,
    GraphChangeParameterValue,
    LoweredGraphChangeParameter,
)
from dcc_mcp_substancedesigner.graph_state import build_graph_state, validate_lineage
from dcc_mcp_substancedesigner.input_types import (
    ControlTargetInput,
    ControlUpdatesInput,
    NestedGraphStateInput,
    NodeIdInput,
    OptionalColorInput,
    OptionalControlTargetInput,
    OptionalGraphIdentifierInput,
    OptionalNodeIdInput,
    OptionalPositionInput,
    OptionalReferenceInput,
    OptionalResolutionDimensionInput,
    OptionalResolutionInput,
    OptionalSkillObjectInput,
    PositionInput,
    ResolutionInput,
    SkillObjectInput,
)
from dcc_mcp_substancedesigner.json_types import JsonValue
from dcc_mcp_substancedesigner.nested_graph_state import (
    NestedGraphStateValidationError,
    diff_nested_graph_state,
    normalize_nested_graph_state_for_apply,
    validate_nested_graph_state,
)
from dcc_mcp_substancedesigner.node_inspection import build_node_inspection
from dcc_mcp_substancedesigner.reference_links import reference_uris_for_graph_state, reference_uris_for_node_detail
from dcc_mcp_substancedesigner.schema import (
    normalize_graph_summary,
    normalize_node_detail,
    normalize_operation_result,
    normalize_packages,
    normalize_scene_info,
)

ENV_SD_BRIDGE_HOST = "DCC_MCP_SUBSTANCEDESIGNER_HOST"
ENV_SD_BRIDGE_PORT = "DCC_MCP_SUBSTANCEDESIGNER_PORT"


class SubstanceDesignerValidationError(ValueError):
    """Raised when adapter input validation fails before contacting the host."""


def client_from_env() -> SubstanceDesignerBridgeClient:
    """Build a bridge client from environment variables."""
    host = os.environ.get(ENV_SD_BRIDGE_HOST, "127.0.0.1")
    port_text = os.environ.get(ENV_SD_BRIDGE_PORT, str(DEFAULT_SD_BRIDGE_PORT))
    host = _required_text(host, ENV_SD_BRIDGE_HOST)
    port = _positive_int(port_text, ENV_SD_BRIDGE_PORT)
    return SubstanceDesignerBridgeClient(host=host, port=port)


@dataclass
class SubstanceDesignerCommands:
    """Typed facade over plugin command names."""

    client: SubstanceDesignerBridgeClient

    def get_scene_info(self, *, include_raw: bool = False) -> Dict[str, Any]:
        raw = self.client.command("get_scene_info")
        normalized = normalize_scene_info(raw)
        return _with_raw(normalized, raw, include_raw)

    def list_graphs(
        self,
        *,
        package_path: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        package_path = _optional_text(package_path, "package_path")
        raw = self.client.command("get_scene_info")
        normalized = normalize_packages(raw, package_path=package_path)
        graphs = []
        for package in normalized["packages"]:
            for graph in package["graphs"]:
                graphs.append(
                    {
                        **graph,
                        "package_path": package["file_path"],
                        "package_index": package["index"],
                    }
                )
        payload = {"graphs": graphs, "graph_count": len(graphs)}
        return _with_raw(payload, raw, include_raw)

    def _get_graph_info(
        self,
        *,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_limit: int = 100,
        include_connections: bool = True,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_limit = _non_negative_int(node_limit, "node_limit")
        params = {
            "graph_identifier": graph_identifier,
            "node_limit": node_limit,
            "include_connections": include_connections,
        }
        raw = self.client.command("get_graph_info", _compact(params))
        normalized = normalize_graph_summary(raw)
        return _with_raw(normalized, raw, include_raw)

    def get_node_detail(
        self,
        *,
        node_id: NodeIdInput,
        graph_ref: OptionalSkillObjectInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        graph_ref = _optional_dict(graph_ref, "graph_ref")
        if graph_ref is not None:
            normalized_ref = normalize_graph_ref(graph_ref)
            if normalized_ref["kind"] != "package_graph":
                graph = self.get_graph_state(
                    graph_ref=normalized_ref,
                    node_ids=[node_id],
                    detail_level="full",
                    include_raw=include_raw,
                )
                nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
                node = next(
                    (
                        item
                        for item in nodes
                        if isinstance(item, dict) and str(item.get("id") or item.get("identifier")) == node_id
                    ),
                    None,
                )
                if node is None:
                    raise SubstanceDesignerValidationError("node '{}' was not found in graph_ref".format(node_id))
                return {
                    "operation": "get_node",
                    "node_id": node_id,
                    "graph_ref": normalized_ref,
                    "graph_context": graph.get("graph_context"),
                    "reference_uris": _graph_ref_reference_uris(normalized_ref),
                    "next_tools": _graph_next_tools(normalized_ref),
                    **node,
                }
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command("get_node_info", _compact({"node_id": node_id, "graph_identifier": graph_identifier}))
        normalized = normalize_node_detail(raw)
        normalized = _enrich_node_definition_identity(normalized)
        normalized = _enrich_node_parameter_metadata(normalized)
        normalized = _enrich_node_with_editable_property_graphs(normalized, graph_identifier=graph_identifier)
        normalized["preview_contract"] = _preview_contract()
        normalized["reference_uris"] = reference_uris_for_node_detail(normalized)
        return _with_raw(normalized, raw, include_raw)

    def inspect_node(
        self,
        *,
        node_id: OptionalNodeIdInput = None,
        definition_id: Optional[str] = None,
        resource_url: Optional[str] = None,
        property_id: Optional[str] = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _optional_node_id(node_id, "node_id")
        definition_id = _optional_text(definition_id, "definition_id")
        resource_url = _optional_text(resource_url, "resource_url")
        property_id = _optional_text(property_id, "property_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        if sum(bool(value) for value in (node_id, definition_id, resource_url)) != 1:
            raise SubstanceDesignerValidationError(
                "inspect_node requires exactly one of node_id, definition_id, or resource_url"
            )
        raw = self.client.command(
            "inspect_node",
            _compact(
                {
                    "node_id": node_id,
                    "definition_id": definition_id,
                    "resource_url": resource_url,
                    "property_id": property_id,
                    "graph_identifier": graph_identifier,
                }
            ),
        )
        normalized = build_node_inspection(raw if isinstance(raw, dict) else {"value": raw})
        return _with_raw(normalized, raw, include_raw)

    def search_node_reference(
        self,
        *,
        query: str,
        kind: Optional[str] = None,
        category: Optional[str] = None,
        graph_scope: Optional[str] = None,
        limit: int = 10,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        query = _required_text(query, "query")
        kind = _optional_text(kind, "kind")
        category = _optional_text(category, "category")
        graph_scope = _optional_text(graph_scope, "graph_scope")
        limit = _positive_int(limit, "limit")
        raw = search_node_references(
            query,
            kind=kind,
            category=category,
            graph_scope=graph_scope,
            limit=limit,
        )
        return _operation("search_node_reference", raw, include_raw)

    def get_preview(
        self,
        *,
        node_id: OptionalNodeIdInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_output_id: Optional[str] = None,
        channel: str = "rgba",
        resolution: str = "small",
        timeout_ms: int = 10000,
        width: OptionalResolutionDimensionInput = None,
        height: OptionalResolutionDimensionInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _optional_node_id(node_id, "node_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_output_id = _optional_text(node_output_id, "node_output_id")
        channel = _required_text(channel, "channel")
        resolution = _resolution_preset(resolution)
        timeout_ms = _positive_int(timeout_ms, "timeout_ms")
        width = _optional_positive_int(width, "width")
        height = _optional_positive_int(height, "height")
        if node_id is not None and (width is not None or height is not None):
            raise SubstanceDesignerValidationError(
                "node_output previews use resolution; width and height are only supported for graph_3d_view / 3D View previews"
            )
        raw = self.client.command(
            "get_preview",
            _compact(
                {
                    "node_id": node_id,
                    "graph_identifier": graph_identifier,
                    "node_output_id": node_output_id,
                    "channel": channel,
                    "resolution": resolution,
                    "timeout_ms": timeout_ms,
                    "width": width,
                    "height": height,
                }
            ),
        )
        return _preview_operation(raw, include_raw)

    def export_output(
        self,
        *,
        node_id: NodeIdInput,
        file_path: str,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_output_id: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        file_path = _required_text(file_path, "file_path")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_output_id = _optional_text(node_output_id, "node_output_id")
        raw = self.client.command(
            "export_output",
            _compact(
                {
                    "node_id": node_id,
                    "file_path": file_path,
                    "graph_identifier": graph_identifier,
                    "node_output_id": node_output_id,
                }
            ),
        )
        return _operation("export_output", raw, include_raw)

    def get_graph_state(
        self,
        *,
        graph_ref: OptionalSkillObjectInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        owner_node_id: OptionalNodeIdInput = None,
        property_id: OptionalReferenceInput = None,
        graph_type: Optional[str] = None,
        node_limit: int = 500,
        node_ids: list[NodeIdInput] | None = None,
        position_bounds: OptionalSkillObjectInput = None,
        include_node_details: bool = False,
        include_parameters: bool = False,
        detail_level: str = "structure",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_ref = _optional_dict(graph_ref, "graph_ref")
        owner_node_id = _optional_node_id(owner_node_id, "owner_node_id")
        property_id = _optional_port_ref(property_id, "property_id")
        graph_type = _optional_text(graph_type, "graph_type")
        if graph_ref is None and owner_node_id and property_id:
            graph_ref = {
                "kind": "node_property_graph",
                **_compact({"graph_identifier": graph_identifier}),
                "node_id": owner_node_id,
                "property": property_id,
                **_compact({"graph_type": graph_type}),
            }
        node_id_filter = _optional_node_id_set(node_ids)
        bounds_filter = _optional_position_bounds(position_bounds)
        if graph_ref is not None:
            normalized_ref = normalize_graph_ref(graph_ref)
            normalized_ref = self._graph_ref_with_inferred_owner_definition(normalized_ref)
            if normalized_ref["kind"] == "fx_map_graph":
                raw = self.client.command(
                    "get_fx_map_graph_state",
                    _compact(
                        {
                            "node_id": normalized_ref["owner_node_id"],
                            "graph_identifier": normalized_ref.get("graph_identifier"),
                        }
                    ),
                )
                state = raw if isinstance(raw, dict) else {"value": raw}
                nodes = _filter_graph_change_nodes(state.get("nodes", []), node_id_filter, bounds_filter)
                selected_ids = _selected_graph_change_node_ids(nodes) if node_id_filter is None else node_id_filter
                connections = _filter_graph_change_connections(state.get("connections", []), selected_ids)
                partial_view = _is_partial_graph_view(node_id_filter, bounds_filter)
                state_hash = (
                    _graph_state_hash(
                        {
                            "graph_type": state.get("graph_type") or "SDSBSFxMapGraph",
                            "nodes": nodes,
                            "connections": connections,
                            "output": state.get("output"),
                        }
                    )
                    if not partial_view
                    else None
                )
                return _with_raw(
                    {
                        "operation": "get_graph",
                        "graph_ref": normalized_ref,
                        "graph_context": resolve_graph_context(graph_ref=normalized_ref, context=None),
                        "graph_type": state.get("graph_type") or "SDSBSFxMapGraph",
                        "exists": state.get("exists", True),
                        "nodes": nodes,
                        "connections": connections,
                        "canonical_connections": _canonical_graph_change_connections(connections),
                        "output": state.get("output"),
                        **_compact({"state_hash": state_hash}),
                        **_partial_graph_view_metadata(partial_view),
                        "diagnostics": state.get("diagnostics", []),
                        "reference_uris": _graph_ref_reference_uris(normalized_ref),
                        "next_tools": _graph_next_tools(normalized_ref, include_replace=not partial_view),
                    },
                    raw,
                    include_raw,
                )
            if normalized_ref["kind"] == "node_property_graph":
                raw = self.client.command(
                    "get_nested_graph_state",
                    _compact(
                        {
                            "node_id": normalized_ref["owner_node_id"],
                            "property_id": normalized_ref["property_id"],
                            "graph_identifier": normalized_ref.get("parent_graph"),
                            "graph_type": normalized_ref.get("graph_type") or "SDSBSFunctionGraph",
                        }
                    ),
                )
                state = raw if isinstance(raw, dict) else {"value": raw}
                nodes = _filter_graph_change_nodes(state.get("nodes", []), node_id_filter, bounds_filter)
                selected_ids = _selected_graph_change_node_ids(nodes) if node_id_filter is None else node_id_filter
                connections = _filter_graph_change_connections(state.get("connections", []), selected_ids)
                if detail_level in {"full", "debug"} or include_node_details:
                    nodes = _enrich_graph_change_nodes_with_definition_ports(nodes)
                partial_view = _is_partial_graph_view(node_id_filter, bounds_filter)
                state_hash = (
                    _graph_state_hash(
                        {
                            "graph_type": state.get("graph_type"),
                            "nodes": nodes,
                            "connections": connections,
                            "output": state.get("output"),
                        }
                    )
                    if not partial_view
                    else None
                )
                return _with_raw(
                    {
                        "operation": "get_graph",
                        "graph_ref": normalized_ref,
                        "graph_context": resolve_graph_context(graph_ref=normalized_ref, context=None),
                        "graph_type": state.get("graph_type"),
                        "exists": state.get("exists", True),
                        "nodes": nodes,
                        "connections": connections,
                        "canonical_connections": _canonical_graph_change_connections(connections),
                        "output": state.get("output"),
                        **_compact({"state_hash": state_hash}),
                        **_partial_graph_view_metadata(partial_view),
                        "diagnostics": state.get("diagnostics", []),
                        "reference_uris": _graph_ref_reference_uris(normalized_ref),
                        "next_tools": _graph_next_tools(normalized_ref, include_replace=not partial_view),
                    },
                    raw,
                    include_raw,
                )
            graph_identifier = normalized_ref.get("graph_identifier") or graph_identifier
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_limit = _non_negative_int(node_limit, "node_limit")
        detail_level = _detail_level(detail_level)
        summary = self._get_graph_info(
            graph_identifier=graph_identifier,
            node_limit=node_limit,
            include_connections=True,
            include_raw=False,
        )
        details = {}
        if include_node_details or include_parameters or detail_level in {"semantic", "full", "debug"}:
            for node in summary["nodes"]:
                node_id = node.get("identifier")
                if node_id:
                    details[str(node_id)] = self.get_node_detail(
                        node_id=str(node_id),
                        graph_identifier=graph_identifier,
                        include_raw=False,
                    )
        state = build_graph_state(summary, details)
        state["detail_level"] = detail_level
        state["include_parameters"] = bool(include_parameters)
        graph_ref_payload = {"kind": "package_graph", **_compact({"graph_identifier": state.get("identifier")})}
        state["operation"] = "get_graph"
        state["graph_ref"] = graph_ref_payload
        if node_id_filter is not None or bounds_filter is not None:
            state = _filter_package_graph_state(state, node_id_filter, bounds_filter)
        else:
            state.update(_partial_graph_view_metadata(False))
        state["reference_uris"] = reference_uris_for_graph_state(state)
        state["next_tools"] = _graph_next_tools(graph_ref_payload)
        return _with_raw(state, summary, include_raw)

    def replace_graph_state(
        self,
        *,
        graph_ref: SkillObjectInput,
        state: SkillObjectInput,
        expected_current_hash: str,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Replace a complete nested graph state when the caller proves it saw the current state."""
        graph_ref = self._graph_ref_with_inferred_owner_definition(
            normalize_graph_ref(_required_dict(graph_ref, "graph_ref"))
        )
        state = _required_dict(state, "state")
        expected_current_hash = _required_text(expected_current_hash, "expected_current_hash")
        current = self.get_graph_state(graph_ref=graph_ref, detail_level="structure", include_raw=False)
        if current.get("partial_view") is True:
            raise SubstanceDesignerValidationError("replace_graph_state requires a complete current graph view")
        current_hash = _required_text(current.get("state_hash"), "current.state_hash")
        if current_hash != expected_current_hash:
            raise SubstanceDesignerValidationError(
                "current graph state hash does not match expected_current_hash; inspect get_graph again before replacing"
            )
        if graph_ref["kind"] == "package_graph":
            raise SubstanceDesignerValidationError("replace_graph_state does not support package_graph replacement")
        if graph_ref["kind"] == "fx_map_graph":
            replace_state = {
                "graph_kind": "fx_map_graph",
                "target": _compact(
                    {
                        "graph_identifier": graph_ref.get("graph_identifier"),
                        "node_id": graph_ref.get("owner_node_id"),
                    }
                ),
                "graph_type": graph_ref.get("graph_type") or "SDSBSFxMapGraph",
                "nodes": _dict_items(state.get("nodes")),
                "connections": _dict_items(state.get("connections")),
                "output": state.get("output") if isinstance(state.get("output"), dict) else None,
            }
            raw = self.client.command("apply_fx_map_graph_state", {"state": replace_state, "mode": "replace"})
            return _operation(
                "replace_graph_state",
                {
                    "applied": True,
                    "replace_strategy": "replace_fx_map_graph",
                    "previous_state_hash": current_hash,
                    "execution_trace": [_execution_trace("apply_fx_map_graph_state")],
                    "result": _sanitize_bridge_payload(raw),
                    "next_tools": _post_apply_next_tools(graph_ref),
                },
                include_raw,
            )
        replace_state = {
            "target": {
                "graph_identifier": graph_ref.get("parent_graph"),
                "node_id": graph_ref["owner_node_id"],
                "property": graph_ref["property_id"],
            },
            "graph_type": graph_ref.get("graph_type") or "SDSBSFunctionGraph",
            "nodes": _dict_items(state.get("nodes")),
            "connections": _dict_items(state.get("connections")),
            "output": state.get("output") if isinstance(state.get("output"), dict) else state.get("output"),
        }
        raw = self.client.command("apply_nested_graph_state", {"state": replace_state, "mode": "replace"})
        return _operation(
            "replace_graph_state",
            {
                "applied": True,
                "replace_strategy": "replace_property_graph",
                "previous_state_hash": current_hash,
                "execution_trace": [_execution_trace("apply_nested_graph_state")],
                "result": _sanitize_bridge_payload(raw),
                "next_tools": _post_apply_next_tools(graph_ref),
            },
            include_raw,
        )

    def get_graph_outputs(
        self,
        *,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_limit: int = 500,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_limit = _non_negative_int(node_limit, "node_limit")
        state = self.get_graph_state(
            graph_identifier=graph_identifier,
            node_limit=node_limit,
            detail_level="semantic",
            include_raw=False,
        )
        raw = graph_outputs(state)
        return _operation("get_graph_outputs", raw, include_raw)

    def trace_output(
        self,
        *,
        output_identifier: str,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_limit: int = 1000,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        output_identifier = _required_text(output_identifier, "output_identifier")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_limit = _non_negative_int(node_limit, "node_limit")
        state = self.get_graph_state(
            graph_identifier=graph_identifier,
            node_limit=node_limit,
            detail_level="semantic",
            include_raw=False,
        )
        raw = trace_output(state, output_identifier)
        return _operation("trace_output", raw, include_raw)

    def summarize_graph(
        self,
        *,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_limit: int = 1000,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_limit = _non_negative_int(node_limit, "node_limit")
        state = self.get_graph_state(
            graph_identifier=graph_identifier,
            node_limit=node_limit,
            detail_level="semantic",
            include_raw=False,
        )
        raw = summarize_graph(state)
        raw["reference_uris"] = reference_uris_for_graph_state(state)
        return _operation("summarize_graph", raw, include_raw)

    def validate_graph_lineage(
        self,
        *,
        source_node_id: NodeIdInput,
        target_node_id: OptionalNodeIdInput = None,
        target_output_identifier: Optional[str] = None,
        source_output: Optional[str] = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        node_limit: int = 1000,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        source_node_id = _required_node_id(source_node_id, "source_node_id")
        target_node_id = _optional_node_id(target_node_id, "target_node_id")
        target_output_identifier = _optional_text(target_output_identifier, "target_output_identifier")
        source_output = _optional_text(source_output, "source_output")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        node_limit = _non_negative_int(node_limit, "node_limit")
        if not target_node_id and not target_output_identifier:
            raise SubstanceDesignerValidationError(
                "validate_graph_lineage requires target_node_id or target_output_identifier"
            )
        state = self.get_graph_state(
            graph_identifier=graph_identifier,
            node_limit=node_limit,
            include_node_details=bool(target_output_identifier),
            include_raw=False,
        )
        raw = validate_lineage(
            state,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            target_output_identifier=target_output_identifier,
            source_output=source_output,
        )
        raw["graph_identifier"] = state.get("identifier")
        return _operation("validate_graph_lineage", raw, include_raw)

    def get_authoring_capabilities(
        self,
        *,
        graph_ref: OptionalSkillObjectInput = None,
        context: OptionalSkillObjectInput = None,
        intent: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Return context-specific graph authoring capabilities for LLM-driven edits."""
        graph_ref = _optional_dict(graph_ref, "graph_ref")
        context = _optional_context(context)
        intent = _optional_text(intent, "intent")
        if graph_ref is not None:
            graph_ref = self._graph_ref_with_inferred_owner_definition(normalize_graph_ref(graph_ref))
        raw = authoring_capabilities(graph_ref=graph_ref, context=context, intent=intent)
        return _operation("get_authoring_capabilities", raw, include_raw)

    def get_authoring_plan(
        self,
        *,
        graph_ref: OptionalSkillObjectInput = None,
        context: OptionalSkillObjectInput = None,
        intent: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Return a bounded authoring plan before concrete graph capabilities."""
        graph_ref = _optional_dict(graph_ref, "graph_ref")
        context = _optional_context(context)
        intent = _optional_text(intent, "intent")
        if graph_ref is not None:
            graph_ref = self._graph_ref_with_inferred_owner_definition(normalize_graph_ref(graph_ref))
        raw = authoring_plan(graph_ref=graph_ref, context=context, intent=intent)
        return _operation("get_authoring_plan", raw, include_raw)

    def validate_graph_change(
        self,
        *,
        change: OptionalSkillObjectInput = None,
        graph_ref: OptionalSkillObjectInput = None,
        context: OptionalSkillObjectInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Validate a declarative graph change against the resolved graph context."""
        graph_ref = _optional_dict(graph_ref, "graph_ref")
        context = _optional_context(context)
        change = normalize_graph_change_parameters(_optional_dict(change, "change"))
        if graph_ref is not None:
            graph_ref = self._graph_ref_with_inferred_owner_definition(normalize_graph_ref(graph_ref))
        raw = validate_graph_change(graph_ref=graph_ref, context=context, change=change)
        return _operation("validate_graph_change", raw, include_raw)

    def apply_graph_change(
        self,
        *,
        change: OptionalSkillObjectInput = None,
        graph_ref: OptionalSkillObjectInput = None,
        context: OptionalSkillObjectInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Validate and apply a declarative graph change."""
        graph_ref = _required_dict(graph_ref, "graph_ref")
        context = _optional_context(context)
        change = normalize_graph_change_parameters(_required_dict(change, "change"))
        graph_ref = self._graph_ref_with_inferred_owner_definition(normalize_graph_ref(graph_ref))
        validation = validate_graph_change(graph_ref=graph_ref, context=context, change=change)
        operation_plan = validation.get("operation_plan") if isinstance(validation.get("operation_plan"), dict) else {}
        if not validation["valid"] or operation_plan.get("apply_ready") is False:
            return _operation(
                "apply_graph_change",
                {
                    "applied": False,
                    "validation": validation,
                    "errors": validation["errors"],
                    "reference_uris": validation.get("reference_uris", []),
                    "next_tools": validation.get("next_tools", []),
                },
                include_raw,
            )
        normalized_ref = normalize_graph_ref(graph_ref)
        if normalized_ref["kind"] == "package_graph":
            if _dict_items(change.get("operations")):
                raw = self._apply_package_graph_patch(
                    normalized_ref=normalized_ref, change=change, validation=validation
                )
            else:
                raw = self._apply_package_graph_change(
                    normalized_ref=normalized_ref, change=change, validation=validation
                )
        elif normalized_ref["kind"] == "fx_map_graph":
            if _dict_items(change.get("operations")):
                raw = self._apply_fx_map_graph_patch(
                    normalized_ref=normalized_ref, change=change, validation=validation
                )
            elif _property_graph_parameter_patch(change):
                raw = self._apply_fx_map_graph_patch(
                    normalized_ref=normalized_ref,
                    change=_parameter_patch_change(change),
                    validation=validation,
                )
            else:
                raw = self._apply_fx_map_graph_patch(
                    normalized_ref=normalized_ref,
                    change=_graph_change_patch(change),
                    validation=validation,
                )
        else:
            if _dict_items(change.get("operations")):
                raw = self._apply_nested_graph_patch(
                    normalized_ref=normalized_ref, change=change, validation=validation
                )
            elif _property_graph_parameter_patch(change):
                raw = self._apply_nested_graph_patch(
                    normalized_ref=normalized_ref,
                    change=_parameter_patch_change(change),
                    validation=validation,
                )
            else:
                raw = self._apply_nested_graph_patch(
                    normalized_ref=normalized_ref,
                    change=_graph_change_patch(change),
                    validation=validation,
                )
        return _operation("apply_graph_change", _compact_apply_graph_change_result(raw), include_raw)

    def _graph_ref_with_inferred_owner_definition(self, graph_ref: Dict[str, Any]) -> Dict[str, Any]:
        """Fill owner_definition for property graphs when the owner node can be inspected."""
        if graph_ref.get("kind") != "node_property_graph":
            return graph_ref
        owner_definition = _optional_text(graph_ref.get("owner_definition"), "graph_ref.owner_definition")
        if owner_definition and not _definition_needs_instance_resolution(owner_definition):
            return graph_ref
        resolved = resolve_graph_context(graph_ref=graph_ref, context=None)
        if resolved.get("confidence") == "high" and resolved.get("contract", {}).get("kind") != "unknown":
            return graph_ref
        owner_node_id = _optional_text(graph_ref.get("owner_node_id"), "graph_ref.owner_node_id")
        if not owner_node_id:
            return graph_ref
        try:
            owner = self.get_node_detail(
                node_id=owner_node_id,
                graph_identifier=_optional_text(graph_ref.get("parent_graph"), "graph_ref.parent_graph"),
                include_raw=False,
            )
        except Exception:
            return graph_ref
        definition = _optional_text(
            owner.get("resolved_definition") or owner.get("definition"),
            "owner.definition",
        )
        if not definition:
            return graph_ref
        return {**graph_ref, "owner_definition": definition}

    def _apply_fx_map_graph_patch(
        self,
        *,
        normalized_ref: Dict[str, Any],
        change: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        patch = {
            "graph_kind": "fx_map_graph",
            "target": _compact(
                {
                    "graph_identifier": normalized_ref.get("graph_identifier"),
                    "node_id": normalized_ref.get("owner_node_id"),
                }
            ),
            "graph_type": normalized_ref.get("graph_type"),
            "operations": _dict_items(change.get("operations")),
        }
        raw_apply = self.client.command("apply_fx_map_graph_patch", {"patch": patch, "mode": "patch"})
        return {
            "applied": True,
            "apply_strategy": "patch_fx_map_graph",
            "validation": validation,
            "execution_trace": [_execution_trace("apply_fx_map_graph_patch")],
            "patch": patch,
            "result": _sanitize_bridge_payload(raw_apply),
            "reference_uris": validation.get("reference_uris", []),
            "next_tools": _post_apply_next_tools(normalized_ref),
        }

    def _apply_nested_graph_patch(
        self,
        *,
        normalized_ref: Dict[str, Any],
        change: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        patch = {
            "graph_kind": "node_property_graph",
            "target": _compact(
                {
                    "graph_identifier": normalized_ref.get("parent_graph"),
                    "node_id": normalized_ref.get("owner_node_id"),
                    "property": normalized_ref.get("property_id"),
                }
            ),
            "graph_type": normalized_ref.get("graph_type"),
            "operations": _dict_items(change.get("operations")),
        }
        raw_apply = self.client.command("apply_nested_graph_patch", {"patch": patch, "mode": "patch"})
        return {
            "applied": True,
            "apply_strategy": "patch_property_graph",
            "validation": validation,
            "execution_trace": [_execution_trace("apply_nested_graph_patch")],
            "patch": patch,
            "result": _sanitize_bridge_payload(raw_apply),
            "parameter_results": _parameter_results_for_operations(patch["operations"]),
            "reference_uris": validation.get("reference_uris", []),
            "next_tools": _post_apply_next_tools(normalized_ref),
        }

    def _apply_package_graph_patch(
        self,
        *,
        normalized_ref: Dict[str, Any],
        change: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        graph_identifier = _optional_text(normalized_ref.get("graph_identifier"), "graph_identifier")
        node_map: Dict[str, str] = {}
        created_nodes: list[Dict[str, Any]] = []
        rewired_inputs: dict[tuple[str, str], list[Dict[str, Any]]] = {}
        parameter_snapshots: dict[tuple[str, str], Dict[str, Any]] = {}
        position_snapshots: dict[str, JsonValue] = {}
        execution_trace = []
        operation_results = []
        pending_step: Dict[str, Any] | None = None
        try:
            for operation in _dict_items(change.get("operations")):
                op = _required_text(operation.get("op"), "change.operations[].op")
                if op == "ensure_node":
                    logical_id = _required_text(operation.get("id") or operation.get("node"), "change.operations[].id")
                    definition = _required_text(operation.get("definition"), "change.operations[].definition")
                    pending_step = {"operation": "create_node", "node": logical_id, "definition": definition}
                    created = self._create_graph_change_node(
                        definition=definition,
                        graph_identifier=graph_identifier,
                        position=operation.get("position"),
                    )
                    execution_trace.append(_execution_trace(created["operation"]))
                    pending_step = None
                    created_result = created.get("result") if isinstance(created.get("result"), dict) else {}
                    created_node_id = _created_node_id(created_result, fallback=logical_id)
                    node_map[logical_id] = created_node_id
                    created_nodes.append(
                        {
                            "id": logical_id,
                            "node_id": created_node_id,
                            "definition": definition,
                            **_compact({"resource_url": created_result.get("resource_url")}),
                            "result": created_result,
                        }
                    )
                    operation_results.append(created_result)
                    for parameter_id, parameter in _graph_change_parameter_items(operation):
                        value, value_type = _parameter_value_and_type(
                            parameter,
                            definition=definition,
                            parameter_id=parameter_id,
                        )
                        target_node = node_map.get(logical_id, logical_id)
                        pending_step = {
                            "operation": "set_parameter",
                            "node": logical_id,
                            "resolved_node_id": target_node,
                            "parameter": parameter_id,
                        }
                        result = self.set_parameter(
                            node_id=target_node,
                            parameter_id=parameter_id,
                            value=value,
                            value_type=value_type,
                            graph_identifier=graph_identifier,
                            include_raw=False,
                        )
                        execution_trace.append(_execution_trace(result["operation"]))
                        pending_step = None
                        operation_results.append(result.get("result"))
                elif op == "set_parameter":
                    target_node = _required_text(operation.get("node"), "change.operations[].node")
                    parameter_id = _required_text(operation.get("parameter"), "change.operations[].parameter")
                    resolved_target = node_map.get(target_node, target_node)
                    if target_node not in node_map:
                        self._snapshot_package_parameter(
                            graph_identifier=graph_identifier,
                            node_id=resolved_target,
                            parameter_id=parameter_id,
                            parameter_snapshots=parameter_snapshots,
                        )
                    pending_step = {
                        "operation": "set_parameter",
                        "node": target_node,
                        "resolved_node_id": resolved_target,
                        "parameter": parameter_id,
                    }
                    result = self.set_parameter(
                        node_id=resolved_target,
                        parameter_id=parameter_id,
                        value=operation.get("value"),
                        value_type=_optional_text(
                            operation.get("value_type") or operation.get("type"), "change.operations[].value_type"
                        )
                        or "float",
                        graph_identifier=graph_identifier,
                        include_raw=False,
                    )
                    execution_trace.append(_execution_trace(result["operation"]))
                    pending_step = None
                    operation_results.append(result.get("result"))
                elif op == "ensure_connection":
                    source, source_output = _graph_change_connection_endpoint(operation, "from")
                    target, target_input = _graph_change_connection_endpoint(operation, "to")
                    resolved_target = node_map.get(target, target)
                    if target not in node_map:
                        self._snapshot_and_disconnect_package_input(
                            graph_identifier=graph_identifier,
                            node_id=resolved_target,
                            input_id=target_input,
                            rewired_inputs=rewired_inputs,
                            execution_trace=execution_trace,
                        )
                    pending_step = {
                        "operation": "connect_nodes",
                        "from": source,
                        "resolved_from_node_id": node_map.get(source, source),
                        "to": target,
                        "resolved_to_node_id": resolved_target,
                        "from_output": source_output,
                        "to_input": target_input,
                    }
                    result = self.connect_nodes(
                        from_node_id=node_map.get(source, source),
                        to_node_id=resolved_target,
                        from_output=source_output,
                        to_input=target_input,
                        graph_identifier=graph_identifier,
                        include_raw=False,
                    )
                    execution_trace.append(_execution_trace(result["operation"]))
                    pending_step = None
                    operation_results.append(result.get("result"))
                elif op == "remove_connection":
                    target, target_input = _graph_change_connection_endpoint(operation, "to")
                    resolved_target = node_map.get(target, target)
                    self._snapshot_and_disconnect_package_input(
                        graph_identifier=graph_identifier,
                        node_id=resolved_target,
                        input_id=target_input,
                        rewired_inputs=rewired_inputs,
                        execution_trace=execution_trace,
                    )
                    pending_step = {
                        "operation": "disconnect_nodes",
                        "node": target,
                        "resolved_node_id": resolved_target,
                        "input": target_input,
                    }
                    pending_step = None
                    operation_results.append({"disconnected": f"{resolved_target}:{target_input}"})
                elif op == "move_node":
                    target_node = _required_text(operation.get("node"), "change.operations[].node")
                    position = operation.get("position")
                    if not isinstance(position, list) or len(position) < 2:
                        raise SubstanceDesignerValidationError("change.operations[].position must be [x, y]")
                    resolved_target = node_map.get(target_node, target_node)
                    if target_node not in node_map:
                        self._snapshot_package_position(
                            graph_identifier=graph_identifier,
                            node_id=resolved_target,
                            position_snapshots=position_snapshots,
                        )
                    pending_step = {
                        "operation": "move_node",
                        "node": target_node,
                        "resolved_node_id": resolved_target,
                    }
                    result = self.move_node(
                        node_id=resolved_target,
                        position=position,
                        graph_identifier=graph_identifier,
                        include_raw=False,
                    )
                    execution_trace.append(_execution_trace(result["operation"]))
                    pending_step = None
                    operation_results.append(result.get("result"))
        except Exception as exc:
            failed_step = pending_step or {"operation": "unknown"}
            execution_trace.append(_failed_execution_trace(failed_step, exc))
            rollback = self._rollback_package_graph_change(
                rewired_inputs=rewired_inputs,
                parameter_snapshots=parameter_snapshots,
                position_snapshots=position_snapshots,
                created_nodes=created_nodes,
                graph_identifier=graph_identifier,
            )
            return {
                "applied": False,
                "apply_strategy": "patch_package_graph",
                "validation": validation,
                "execution_trace": execution_trace,
                "node_map": node_map,
                "created_nodes": created_nodes,
                "operations": operation_results,
                "parameter_results": _parameter_results_for_operations(_dict_items(change.get("operations"))),
                "rollback": rollback,
                "rolled_back": rollback["complete"],
                "partial_changes": not rollback["complete"],
                "error": str(exc),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "failed_step": failed_step,
                "reference_uris": validation.get("reference_uris", []),
                "next_tools": _post_apply_next_tools(normalized_ref),
            }
        return {
            "applied": True,
            "apply_strategy": "patch_package_graph",
            "validation": validation,
            "execution_trace": execution_trace,
            "node_map": node_map,
            "created_nodes": created_nodes,
            "operations": operation_results,
            "parameter_results": _parameter_results_for_operations(_dict_items(change.get("operations"))),
            "reference_uris": validation.get("reference_uris", []),
            "next_tools": _post_apply_next_tools(normalized_ref),
        }

    def _apply_package_graph_change(
        self,
        *,
        normalized_ref: Dict[str, Any],
        change: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply a declarative package-graph change through existing bridge primitives."""
        graph_identifier = _optional_text(normalized_ref.get("graph_identifier"), "graph_identifier")
        node_map: Dict[str, str] = {}
        created_nodes = []
        created_logical_ids: set[str] = set()
        rewired_inputs: dict[tuple[str, str], list[Dict[str, Any]]] = {}
        parameter_snapshots: dict[tuple[str, str], Dict[str, Any]] = {}
        position_snapshots: dict[str, JsonValue] = {}
        parameter_results = []
        connection_results = []
        execution_trace = []
        pending_step: Dict[str, Any] | None = None
        try:
            for node in _dict_items(change.get("nodes")):
                logical_id = _required_text(node.get("id"), "change.nodes[].id")
                definition = _optional_text(node.get("definition"), "change.nodes[].definition")
                if _looks_like_existing_host_node_id(logical_id):
                    created_node_id = logical_id
                    node_map[logical_id] = created_node_id
                    if "position" in node:
                        self._snapshot_package_position(
                            graph_identifier=graph_identifier,
                            node_id=created_node_id,
                            position_snapshots=position_snapshots,
                        )
                        move_result = self.move_node(
                            node_id=created_node_id,
                            position=node.get("position"),
                            graph_identifier=graph_identifier,
                            include_raw=False,
                        )
                        execution_trace.append(_execution_trace(move_result["operation"]))
                else:
                    definition = _required_text(definition, "change.nodes[].definition")
                    pending_step = {"operation": "create_node", "node": logical_id, "definition": definition}
                    created = self._create_graph_change_node(
                        definition=definition,
                        graph_identifier=graph_identifier,
                        position=node.get("position"),
                    )
                    execution_trace.append(_execution_trace(created["operation"]))
                    pending_step = None
                    created_result = created.get("result") if isinstance(created.get("result"), dict) else {}
                    created_node_id = _created_node_id(created_result, fallback=logical_id)
                    node_map[logical_id] = created_node_id
                    created_logical_ids.add(logical_id)
                    created_nodes.append(
                        {
                            "id": logical_id,
                            "node_id": created_node_id,
                            "definition": definition,
                            **_compact({"resource_url": created_result.get("resource_url")}),
                            "result": created_result,
                        }
                    )

                for parameter_id, parameter in _graph_change_parameter_items(node):
                    if logical_id not in created_logical_ids and _looks_like_existing_host_node_id(logical_id):
                        self._snapshot_package_parameter(
                            graph_identifier=graph_identifier,
                            node_id=created_node_id,
                            parameter_id=parameter_id,
                            parameter_snapshots=parameter_snapshots,
                        )
                    value, value_type = _parameter_value_and_type(
                        parameter,
                        definition=definition,
                        parameter_id=parameter_id,
                    )
                    pending_step = {
                        "operation": "set_parameter",
                        "node": logical_id,
                        "resolved_node_id": created_node_id,
                        "parameter": parameter_id,
                    }
                    parameter_result = self.set_parameter(
                        node_id=created_node_id,
                        parameter_id=parameter_id,
                        value=value,
                        value_type=value_type,
                        graph_identifier=graph_identifier,
                        include_raw=False,
                    )
                    execution_trace.append(_execution_trace(parameter_result["operation"]))
                    pending_step = None
                    parameter_results.append(parameter_result.get("result"))

            for connection in _dict_items(change.get("connections")):
                source, source_output = _graph_change_connection_endpoint(connection, "from")
                target, target_input = _graph_change_connection_endpoint(connection, "to")
                resolved_target = node_map.get(target, target)
                if target not in created_logical_ids:
                    self._snapshot_and_disconnect_package_input(
                        graph_identifier=graph_identifier,
                        node_id=resolved_target,
                        input_id=target_input,
                        rewired_inputs=rewired_inputs,
                        execution_trace=execution_trace,
                    )
                pending_step = {
                    "operation": "connect_nodes",
                    "from": source,
                    "resolved_from_node_id": node_map.get(source, source),
                    "to": target,
                    "resolved_to_node_id": resolved_target,
                    "from_output": source_output,
                    "to_input": target_input,
                }
                connection_result = self.connect_nodes(
                    from_node_id=node_map.get(source, source),
                    to_node_id=resolved_target,
                    from_output=source_output,
                    to_input=target_input,
                    graph_identifier=graph_identifier,
                    include_raw=False,
                )
                execution_trace.append(_execution_trace(connection_result["operation"]))
                pending_step = None
                connection_results.append(connection_result.get("result"))
        except Exception as exc:
            failed_step = pending_step or {"operation": "unknown"}
            execution_trace.append(_failed_execution_trace(failed_step, exc))
            rollback = self._rollback_package_graph_change(
                rewired_inputs=rewired_inputs,
                parameter_snapshots=parameter_snapshots,
                position_snapshots=position_snapshots,
                created_nodes=created_nodes,
                graph_identifier=graph_identifier,
            )
            return {
                "applied": False,
                "apply_strategy": "merge_package_graph",
                "validation": validation,
                "execution_trace": execution_trace,
                "node_map": node_map,
                "created_nodes": created_nodes,
                "parameters": parameter_results,
                "parameter_results": _parameter_results_for_nodes(_dict_items(change.get("nodes")), node_map=node_map),
                "connections": connection_results,
                "rollback": rollback,
                "rolled_back": rollback["complete"],
                "partial_changes": not rollback["complete"],
                "error": str(exc),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "failed_step": failed_step,
                "reference_uris": validation.get("reference_uris", []),
                "next_tools": _post_apply_next_tools(normalized_ref),
            }

        return {
            "applied": True,
            "apply_strategy": "merge_package_graph",
            "validation": validation,
            "execution_trace": execution_trace,
            "node_map": node_map,
            "created_nodes": created_nodes,
            "parameters": parameter_results,
            "parameter_results": _parameter_results_for_nodes(_dict_items(change.get("nodes")), node_map=node_map),
            "connections": connection_results,
            "reference_uris": validation.get("reference_uris", []),
            "next_tools": _post_apply_next_tools(normalized_ref),
        }

    def _snapshot_and_disconnect_package_input(
        self,
        *,
        graph_identifier: str | None,
        node_id: str,
        input_id: OptionalReferenceInput,
        rewired_inputs: dict[tuple[str, str], list[Dict[str, Any]]],
        execution_trace: list[Dict[str, Any]],
    ) -> None:
        input_ref = _optional_port_ref(input_id, "connection.to_input")
        if input_ref is None:
            raise SubstanceDesignerValidationError("package graph rewire requires an explicit target input")
        key = (node_id, input_ref)
        if key in rewired_inputs:
            return
        previous = self._package_graph_input_connections(
            graph_identifier=graph_identifier,
            node_id=node_id,
            input_id=input_ref,
        )
        rewired_inputs[key] = previous
        result = self.disconnect_nodes(
            node_id=node_id,
            input_id=input_ref,
            graph_identifier=graph_identifier,
            include_raw=False,
        )
        trace = _execution_trace(result["operation"])
        trace["previous_connections"] = [dict(item) for item in previous]
        execution_trace.append(trace)

    def _package_graph_input_connections(
        self,
        *,
        graph_identifier: str | None,
        node_id: str,
        input_id: str,
    ) -> list[Dict[str, Any]]:
        state = self.get_graph_state(graph_identifier=graph_identifier, node_limit=5000, include_raw=False)
        previous = []
        for connection in _dict_items(state.get("connections")):
            if connection.get("to_node") == node_id and connection.get("to_input") == input_id:
                from_node = _optional_text(connection.get("from_node"), "connection.from_node")
                from_output = _optional_text(connection.get("from_output"), "connection.from_output")
                if from_node and from_output:
                    previous.append({"from_node": from_node, "from_output": from_output})
        return previous

    def _snapshot_package_parameter(
        self,
        *,
        graph_identifier: str | None,
        node_id: str,
        parameter_id: str,
        parameter_snapshots: dict[tuple[str, str], Dict[str, Any]],
    ) -> None:
        key = (node_id, parameter_id)
        if key in parameter_snapshots:
            return
        detail = self.get_node_detail(node_id=node_id, graph_identifier=graph_identifier, include_raw=False)
        for container_name in ("inputs", "parameters", "annotations"):
            for item in _dict_items(detail.get(container_name)):
                if item.get("id") != parameter_id:
                    continue
                if "value" not in item and "current_value" not in item:
                    raise SubstanceDesignerValidationError(
                        "cannot rollback parameter '{}.{}': current value is not available".format(node_id, parameter_id)
                    )
                value = item.get("value") if "value" in item else item.get("current_value")
                value_type = item.get("value_type") or item.get("type")
                if isinstance(value_type, list):
                    value_type = value_type[0] if value_type else None
                parameter_snapshots[key] = {
                    "node_id": node_id,
                    "parameter": parameter_id,
                    "value": value,
                    "value_type": str(value_type) if value_type else _infer_parameter_value_type(value),
                }
                return
        raise SubstanceDesignerValidationError(
            "cannot rollback parameter '{}.{}': parameter was not found".format(node_id, parameter_id)
        )

    def _snapshot_package_position(
        self,
        *,
        graph_identifier: str | None,
        node_id: str,
        position_snapshots: dict[str, JsonValue],
    ) -> None:
        if node_id in position_snapshots:
            return
        detail = self.get_node_detail(node_id=node_id, graph_identifier=graph_identifier, include_raw=False)
        position = detail.get("position")
        if not isinstance(position, list) or len(position) < 2:
            raise SubstanceDesignerValidationError("cannot rollback node '{}': current position is not available".format(node_id))
        position_snapshots[node_id] = position

    def _rollback_package_graph_change(
        self,
        *,
        rewired_inputs: dict[tuple[str, str], list[Dict[str, Any]]],
        parameter_snapshots: dict[tuple[str, str], Dict[str, Any]],
        position_snapshots: dict[str, JsonValue],
        created_nodes: list[Dict[str, Any]],
        graph_identifier: str | None,
    ) -> Dict[str, Any]:
        restored = []
        restored_parameters = []
        restored_positions = []
        errors = []
        for (node_id, input_id), previous_connections in reversed(list(rewired_inputs.items())):
            try:
                self.disconnect_nodes(node_id=node_id, input_id=input_id, graph_identifier=graph_identifier, include_raw=False)
                for previous in previous_connections:
                    self.connect_nodes(
                        from_node_id=previous["from_node"],
                        to_node_id=node_id,
                        from_output=previous["from_output"],
                        to_input=input_id,
                        graph_identifier=graph_identifier,
                        include_raw=False,
                    )
                restored.append(
                    {"node_id": node_id, "input": input_id, "connections": [dict(item) for item in previous_connections]}
                )
            except Exception as exc:
                errors.append({"node_id": node_id, "input": input_id, "error": str(exc)})
        for snapshot in reversed(list(parameter_snapshots.values())):
            try:
                self.set_parameter(
                    node_id=snapshot["node_id"],
                    parameter_id=snapshot["parameter"],
                    value=snapshot["value"],
                    value_type=snapshot["value_type"],
                    graph_identifier=graph_identifier,
                    include_raw=False,
                )
                restored_parameters.append(dict(snapshot))
            except Exception as exc:
                errors.append({"node_id": snapshot["node_id"], "parameter": snapshot["parameter"], "error": str(exc)})
        for node_id, position in reversed(list(position_snapshots.items())):
            try:
                self.move_node(node_id=node_id, position=position, graph_identifier=graph_identifier, include_raw=False)
                restored_positions.append({"node_id": node_id, "position": position})
            except Exception as exc:
                errors.append({"node_id": node_id, "position": position, "error": str(exc)})
        node_rollback = self._rollback_package_graph_created_nodes(
            created_nodes=created_nodes,
            graph_identifier=graph_identifier,
        )
        errors.extend(node_rollback["errors"])
        return {
            "complete": not errors,
            "restored_connections": restored,
            "restored_parameters": restored_parameters,
            "restored_positions": restored_positions,
            "deleted": node_rollback["deleted"],
            "errors": errors,
        }

    def _rollback_package_graph_created_nodes(
        self,
        *,
        created_nodes: list[Dict[str, Any]],
        graph_identifier: str | None,
    ) -> Dict[str, Any]:
        deleted = []
        errors = []
        for created in reversed(created_nodes):
            node_id = created.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            try:
                result = self.delete_node(node_id=node_id, graph_identifier=graph_identifier, include_raw=False)
                deleted.append({"node_id": node_id, "result": result.get("result")})
            except Exception as exc:
                errors.append({"node_id": node_id, "error": str(exc)})
        return {"complete": not errors, "deleted": deleted, "errors": errors}

    def _create_graph_change_node(
        self,
        *,
        definition: str,
        graph_identifier: str | None,
        position: JsonValue,
    ) -> Dict[str, Any]:
        creation = _creation_contract_for_definition(definition)
        if creation.get("method") == "create_instance_node":
            resource_url = _required_text(creation.get("resource_url"), "creation.resource_url")
            return self.create_instance_node(
                resource_url=resource_url,
                graph_identifier=graph_identifier,
                position=position,
                package_hint=_package_hint_from_creation(creation),
                include_raw=False,
            )
        return self.create_node(
            definition_id=definition,
            graph_identifier=graph_identifier,
            position=position,
            include_raw=False,
        )

    def create_package(self, *, file_path: Optional[str] = None, include_raw: bool = False) -> Dict[str, Any]:
        file_path = _optional_text(file_path, "file_path")
        raw = self.client.command("create_package", _compact({"file_path": file_path}))
        if isinstance(raw, dict) and "package_index" not in raw:
            inventory = self.client.command("get_scene_info")
            packages = inventory.get("packages", []) if isinstance(inventory, dict) else []
            if isinstance(packages, list) and packages:
                raw = {**raw, "package_index": len(packages) - 1}
        return _operation("create_package", raw, include_raw)

    def create_graph(
        self,
        *,
        graph_name: str = "MCP_Graph",
        package_index: int = 0,
        package_path: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_name = _required_text(graph_name, "graph_name")
        package_index = _non_negative_int(package_index, "package_index")
        package_path = _optional_text(package_path, "package_path")
        raw = self.client.command(
            "create_graph",
            _compact({"graph_name": graph_name, "package_index": package_index, "package_path": package_path}),
        )
        return _operation("create_graph", raw, include_raw)

    def delete_graph(
        self,
        *,
        graph_identifier: str,
        package_index: int = 0,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_identifier = _required_text(graph_identifier, "graph_identifier")
        package_index = _non_negative_int(package_index, "package_index")
        raw = self.client.command(
            "delete_graph",
            {"graph_identifier": graph_identifier, "package_index": package_index},
        )
        return _operation("delete_graph", raw, include_raw)

    def open_graph(self, *, graph_identifier: str, include_raw: bool = False) -> Dict[str, Any]:
        graph_identifier = _required_text(graph_identifier, "graph_identifier")
        raw = self.client.command("open_graph", {"graph_identifier": graph_identifier})
        return _operation("open_graph", raw, include_raw)

    def save_package(
        self,
        *,
        package_index: int = 0,
        file_path: Optional[str] = None,
        package_path: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        package_index = _non_negative_int(package_index, "package_index")
        file_path = _optional_text(file_path, "file_path")
        package_path = _optional_text(package_path, "package_path")
        raw = self.client.command(
            "save_package",
            _compact({"package_index": package_index, "file_path": file_path, "package_path": package_path}),
        )
        return _operation("save_package", raw, include_raw)

    def create_node(
        self,
        *,
        definition_id: Optional[str] = None,
        definition: Optional[str] = None,
        node_type: Optional[str] = None,
        resource_url: Optional[str] = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        position: OptionalPositionInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        definition_id = _node_definition_id(definition_id, definition, node_type, resource_url)
        if definition_id.startswith("pkg://"):
            return self.create_instance_node(
                resource_url=definition_id,
                graph_identifier=graph_identifier,
                position=position,
                include_raw=include_raw,
            )
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        normalized_position = _optional_position(position, "position")
        raw = self.client.command(
            "create_node",
            _compact(
                {"definition_id": definition_id, "graph_identifier": graph_identifier, "position": normalized_position}
            ),
        )
        return _operation("create_node", raw, include_raw)

    def create_instance_node(
        self,
        *,
        resource_url: str,
        graph_identifier: OptionalGraphIdentifierInput = None,
        position: OptionalPositionInput = None,
        package_hint: OptionalSkillObjectInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        resource_url = _required_text(resource_url, "resource_url")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        normalized_position = _optional_position(position, "position")
        package_hint = _optional_dict(package_hint, "package_hint")
        raw = self.client.command(
            "create_instance_node",
            _compact(
                {
                    "resource_url": resource_url,
                    "graph_identifier": graph_identifier,
                    "position": normalized_position,
                    "package_hint": package_hint,
                }
            ),
        )
        return _operation("create_instance_node", raw, include_raw)

    def create_output_node(
        self,
        *,
        usage: str = "baseColor",
        graph_identifier: OptionalGraphIdentifierInput = None,
        position: OptionalPositionInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        usage = _required_text(usage, "usage")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        normalized_position = _optional_position(position, "position")
        raw = self.client.command(
            "create_output_node",
            _compact({"usage": usage, "graph_identifier": graph_identifier, "position": normalized_position}),
        )
        return _operation("create_output_node", raw, include_raw)

    def create_frame(
        self,
        *,
        label: str,
        node_ids: Optional[list[NodeIdInput]] = None,
        description: str = "",
        graph_identifier: OptionalGraphIdentifierInput = None,
        position: OptionalPositionInput = None,
        size: OptionalPositionInput = None,
        padding: float = 160.0,
        color: OptionalColorInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        label = _required_text(label, "label")
        node_ids = [_required_node_id(node_id, "node_ids") for node_id in node_ids] if node_ids is not None else None
        if not isinstance(description, str):
            raise SubstanceDesignerValidationError("description must be a string")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        normalized_position = _optional_position(position, "position")
        normalized_size = _optional_position(size, "size")
        normalized_padding = _positive_number(padding, "padding")
        normalized_color = _optional_color(color, "color")
        raw = self.client.command(
            "create_frame",
            _compact(
                {
                    "label": label,
                    "node_ids": node_ids,
                    "description": description,
                    "graph_identifier": graph_identifier,
                    "position": normalized_position,
                    "size": normalized_size,
                    "padding": normalized_padding,
                    "color": normalized_color,
                }
            ),
        )
        return _operation("create_frame", raw, include_raw)

    def delete_node(
        self,
        *,
        node_id: NodeIdInput,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command("delete_node", _compact({"node_id": node_id, "graph_identifier": graph_identifier}))
        return _operation("delete_node", raw, include_raw)

    def move_node(
        self,
        *,
        node_id: NodeIdInput,
        position: PositionInput,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        normalized_position = _required_position(position, "position")
        raw = self.client.command(
            "move_node",
            _compact({"node_id": node_id, "position": normalized_position, "graph_identifier": graph_identifier}),
        )
        return _operation("move_node", raw, include_raw)

    def duplicate_node(
        self,
        *,
        node_id: NodeIdInput,
        offset: OptionalPositionInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        normalized_offset = _optional_position(offset, "offset")
        raw = self.client.command(
            "duplicate_node",
            _compact({"node_id": node_id, "offset": normalized_offset, "graph_identifier": graph_identifier}),
        )
        return _operation("duplicate_node", raw, include_raw)

    def connect_nodes(
        self,
        *,
        from_node_id: NodeIdInput,
        to_node_id: NodeIdInput,
        from_output: OptionalReferenceInput = None,
        to_input: OptionalReferenceInput = None,
        output: OptionalReferenceInput = None,
        input: OptionalReferenceInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        from_node_id = _required_node_id(from_node_id, "from_node_id")
        to_node_id = _required_node_id(to_node_id, "to_node_id")
        normalized_from_output = _optional_port_ref(from_output if from_output is not None else output, "from_output")
        normalized_to_input = _optional_port_ref(to_input if to_input is not None else input, "to_input")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "connect_nodes",
            _compact(
                {
                    "from_node_id": from_node_id,
                    "to_node_id": to_node_id,
                    "from_output": normalized_from_output,
                    "to_input": normalized_to_input,
                    "graph_identifier": graph_identifier,
                }
            ),
        )
        return _operation("connect_nodes", raw, include_raw)

    def disconnect_nodes(
        self,
        *,
        node_id: NodeIdInput,
        input_id: OptionalReferenceInput = None,
        input: OptionalReferenceInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        normalized_input_id = _optional_port_ref(input_id if input_id is not None else input, "input_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "disconnect_nodes",
            _compact({"node_id": node_id, "input_id": normalized_input_id, "graph_identifier": graph_identifier}),
        )
        return _operation("disconnect_nodes", raw, include_raw)

    def set_parameter(
        self,
        *,
        node_id: NodeIdInput,
        parameter_id: OptionalReferenceInput = None,
        property: OptionalReferenceInput = None,
        property_id: OptionalReferenceInput = None,
        id: OptionalReferenceInput = None,
        control: OptionalReferenceInput = None,
        value: JsonValue = None,
        value_type: str = "float",
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        normalized_parameter_id = _property_ref(parameter_id, property, property_id, id, control)
        _required_value(value, "value")
        value_type = _required_text(value_type, "value_type")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "set_parameter",
            _compact(
                {
                    "node_id": node_id,
                    "parameter_id": normalized_parameter_id,
                    "value": value,
                    "value_type": value_type,
                    "graph_identifier": graph_identifier,
                }
            ),
        )
        return _operation("set_parameter", raw, include_raw)

    def list_controls(
        self,
        *,
        target: ControlTargetInput,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        target = _required_dict(target, "target")
        raw = self.client.command("list_controls", {"target": target})
        return _operation("list_controls", raw, include_raw)

    def set_controls(
        self,
        *,
        target: ControlTargetInput,
        updates: ControlUpdatesInput,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        target = _required_dict(target, "target")
        normalized_updates = _list_of_dicts(updates, "updates")
        raw = self.client.command("set_controls", {"target": target, "updates": normalized_updates})
        return _operation("set_controls", raw, include_raw)

    def list_graph_inputs(
        self,
        *,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command("list_graph_inputs", _compact({"graph_identifier": graph_identifier}))
        return _operation("list_graph_inputs", raw, include_raw)

    def set_graph_input(
        self,
        *,
        input_id: Optional[str] = None,
        value: JsonValue = None,
        value_type: Optional[str] = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        target: OptionalControlTargetInput = None,
        mode: str = "replace",
        description: Optional[str] = None,
        group: Optional[str] = None,
        min: Optional[float] = None,
        max: Optional[float] = None,
        step: Optional[float] = None,
        clamp: Optional[bool] = None,
        editor: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        input_id = _optional_text(input_id, "input_id")
        target = _optional_dict(target, "target")
        if input_id is None and target is None:
            raise SubstanceDesignerValidationError("input_id or target is required")
        if value is None and target is None:
            _required_value(value, "value")
        value_type = _optional_text(value_type, "value_type")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        mode = _required_text(mode, "mode")
        raw = self.client.command(
            "set_graph_input",
            _compact(
                {
                    "input_id": input_id,
                    "value": value,
                    "value_type": value_type,
                    "graph_identifier": graph_identifier,
                    "target": target,
                    "mode": mode,
                    "description": description,
                    "group": group,
                    "min": min,
                    "max": max,
                    "step": step,
                    "clamp": clamp,
                    "editor": editor,
                }
            ),
        )
        return _operation("set_graph_input", raw, include_raw)

    def set_node_comment(
        self,
        *,
        node_id: NodeIdInput,
        comment: str,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        if not isinstance(comment, str):
            raise SubstanceDesignerValidationError("comment must be a string")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "set_node_comment", _compact({"node_id": node_id, "comment": comment, "graph_identifier": graph_identifier})
        )
        return _operation("set_node_comment", raw, include_raw)

    def set_graph_output_size(
        self,
        *,
        width_log2: int = 11,
        height_log2: int = 11,
        width: OptionalResolutionDimensionInput = None,
        height: OptionalResolutionDimensionInput = None,
        size: OptionalResolutionInput = None,
        resolution: OptionalResolutionInput = None,
        graph_identifier: OptionalGraphIdentifierInput = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        if resolution is not None:
            width_log2, height_log2 = _resolution_log2_pair(resolution)
        elif size is not None:
            width_log2, height_log2 = _resolution_log2_pair(size)
        elif width is not None or height is not None:
            width_log2, height_log2 = _resolution_log2_pair({"width": width, "height": height or width})
        else:
            width_log2 = _non_negative_int(width_log2, "width_log2")
            height_log2 = _non_negative_int(height_log2, "height_log2")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "set_graph_output_size",
            _compact({"width_log2": width_log2, "height_log2": height_log2, "graph_identifier": graph_identifier}),
        )
        return _operation("set_graph_output_size", raw, include_raw)

    def diagnostic(self, *, include_raw: bool = False) -> Dict[str, Any]:
        raw = self.client.command("diagnostic")
        if isinstance(raw, dict):
            raw = _diagnostic_public_payload(raw)
            raw = {
                **raw,
                "client_version": _client_version(),
                "client_package_path": os.path.dirname(os.path.abspath(__file__)),
                "python_executable": sys.executable,
            }
        return _operation("diagnostic", raw, include_raw)

    def refresh_plugin(self, *, include_raw: bool = False) -> Dict[str, Any]:
        raw = self.client.command("refresh_plugin")
        return _operation("refresh_plugin", raw, include_raw)

    def load_package(
        self,
        *,
        path: Optional[str] = None,
        package_name: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        path = _optional_text(path, "path")
        package_name = _optional_text(package_name, "package_name")
        if path is None and package_name is None:
            raise ValueError("path or package_name is required")
        raw = self.client.command("load_package", _compact({"path": path, "package_name": package_name}))
        return _operation("load_package", raw, include_raw)

    def arrange_nodes(
        self,
        *,
        graph_identifier: OptionalGraphIdentifierInput = None,
        start_x: float = -1000,
        start_y: float = 0,
        node_spacing_x: float = 200,
        node_spacing_y: float = 150,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        start_x = _number(start_x, "start_x")
        start_y = _number(start_y, "start_y")
        node_spacing_x = _positive_number(node_spacing_x, "node_spacing_x")
        node_spacing_y = _positive_number(node_spacing_y, "node_spacing_y")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "arrange_nodes",
            _compact(
                {
                    "graph_identifier": graph_identifier,
                    "start_x": start_x,
                    "start_y": start_y,
                    "node_spacing_x": node_spacing_x,
                    "node_spacing_y": node_spacing_y,
                }
            ),
        )
        return _operation("arrange_nodes", raw, include_raw)

    def get_nested_graph_state(
        self,
        *,
        node_id: NodeIdInput,
        property_id: str,
        graph_identifier: OptionalGraphIdentifierInput = None,
        graph_type: str = "SDSBSFunctionGraph",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        property_id = _required_text(property_id, "property_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        graph_type = _required_text(graph_type, "graph_type")
        raw = self.client.command(
            "get_nested_graph_state",
            _compact(
                {
                    "node_id": node_id,
                    "property_id": property_id,
                    "graph_identifier": graph_identifier,
                    "graph_type": graph_type,
                }
            ),
        )
        if isinstance(raw, dict):
            raw = {
                **raw,
                "reference_uris": _merge_reference_uris(
                    raw.get("reference_uris", []),
                    [
                        "substancedesigner://authoring/contracts/nested-graph-state",
                        "substancedesigner://authoring/contracts/node-introspection",
                        "substancedesigner://authoring/contracts/owner-input-binding",
                        "substancedesigner://authoring/contracts/operation-safety",
                    ],
                ),
            }
        return _operation("get_nested_graph_state", raw, include_raw)

    def get_pixel_processor_graph(
        self,
        *,
        node_id: NodeIdInput,
        graph_identifier: OptionalGraphIdentifierInput = None,
        property_id: str = "perpixel",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        node_id = _required_node_id(node_id, "node_id")
        property_id = _required_text(property_id, "property_id")
        graph_identifier = _optional_text(graph_identifier, "graph_identifier")
        raw = self.client.command(
            "get_nested_graph_state",
            _compact(
                {
                    "node_id": node_id,
                    "property_id": property_id,
                    "graph_identifier": graph_identifier,
                    "graph_type": "SDSBSFunctionGraph",
                }
            ),
        )
        result = raw if isinstance(raw, dict) else {"value": raw}
        result = {
            **result,
            "pixel_processor": {
                "node_id": node_id,
                "property": property_id,
                "graph_identifier": graph_identifier,
            },
            "reference_uris": _merge_reference_uris(
                result.get("reference_uris", []),
                [
                    "substancedesigner://authoring/contracts/nested-graph-state",
                    "substancedesigner://authoring/contracts/node-introspection",
                    "substancedesigner://authoring/contracts/owner-input-binding",
                    "substancedesigner://authoring/contracts/operation-safety",
                ],
            ),
        }
        return _operation("get_pixel_processor_graph", result, include_raw)

    def validate_nested_graph_state(
        self,
        *,
        state: NestedGraphStateInput,
        mode: str = "sync",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        try:
            raw = validate_nested_graph_state(state, mode=mode)
        except NestedGraphStateValidationError as exc:
            raw = {"valid": False, "mode": mode, "errors": [str(exc)], "reference_uris": [], "state": None}
        return _operation("validate_nested_graph_state", raw, include_raw)

    def diff_nested_graph_state(
        self,
        *,
        desired_state: NestedGraphStateInput,
        current_state: Optional[dict[str, Any]] = None,
        mode: str = "sync",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        if current_state is None:
            desired = _optional_dict(desired_state, "desired_state") or {}
            try:
                normalized = normalize_nested_graph_state_for_apply(desired, mode=mode)
            except NestedGraphStateValidationError as exc:
                raw = {
                    "valid": False,
                    "mode": mode,
                    "status": "invalid",
                    "errors": [str(exc)],
                    "reference_uris": [],
                    "changes": [],
                }
                return _operation("diff_nested_graph_state", raw, include_raw)
            target = normalized["target"]
            current_state = self.client.command(
                "get_nested_graph_state",
                _compact(
                    {
                        "node_id": target["node_id"],
                        "property_id": target["property"],
                        "graph_identifier": target.get("graph_identifier"),
                        "graph_type": normalized["graph_type"],
                    }
                ),
            )
        else:
            current_state = _optional_dict(current_state, "current_state")
        try:
            raw = diff_nested_graph_state(current_state, desired_state, mode=mode)
        except NestedGraphStateValidationError as exc:
            raw = {
                "valid": False,
                "mode": mode,
                "status": "invalid",
                "errors": [str(exc)],
                "reference_uris": [],
                "changes": [],
            }
        return _operation("diff_nested_graph_state", raw, include_raw)

    def apply_nested_graph_state(
        self,
        *,
        state: NestedGraphStateInput,
        mode: str = "sync",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        try:
            normalized = normalize_nested_graph_state_for_apply(state, mode=mode)
        except NestedGraphStateValidationError as exc:
            raise SubstanceDesignerValidationError(f"nested graph state is invalid: {exc}") from exc
        raw = self.client.command("apply_nested_graph_state", {"state": normalized, "mode": mode})
        return _operation("apply_nested_graph_state", raw, include_raw)

    def bind_parameter_input(
        self,
        *,
        target: SkillObjectInput,
        input: dict[str, Any],
        mode: str = "replace",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        target = _required_dict(target, "target")
        input = _required_dict(input, "input")
        mode = _required_text(mode, "mode")
        raw = self.client.command("bind_parameter_input", {"target": target, "input": input, "mode": mode})
        if isinstance(raw, dict):
            graph_ref = _target_to_node_property_graph_ref(target)
            raw = {
                **_sanitize_bridge_payload(raw),
                "next_tools": _post_apply_next_tools(graph_ref) if graph_ref else [],
            }
        return _operation("bind_parameter_input", raw, include_raw)

    def execute_python(
        self,
        *,
        code: str,
        strict_json: bool = False,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        code = _required_text(code, "code")
        raw = self.client.command("execute_python", {"code": code, "strict_json": bool(strict_json)})
        return _execute_python_operation(raw, include_raw)


def commands_from_env() -> SubstanceDesignerCommands:
    """Create the default command facade from environment variables."""
    return SubstanceDesignerCommands(client=client_from_env())


def _with_raw(normalized: Dict[str, Any], raw: Any, include_raw: bool) -> Dict[str, Any]:
    if include_raw:
        return {**normalized, "raw": raw}
    return normalized


def _operation(operation: str, raw: Any, include_raw: bool) -> Dict[str, Any]:
    normalized = normalize_operation_result(operation, raw)
    return _with_raw(normalized, raw, include_raw)


def _graph_state_hash(state: Dict[str, Any]) -> str:
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _graph_ref_reference_uris(graph_ref: Dict[str, Any]) -> list[str]:
    if graph_ref.get("kind") == "package_graph":
        return [
            "substancedesigner://authoring/contracts/reference-first-policy",
            "substancedesigner://authoring/contracts/compositing-graph-state",
            "substancedesigner://authoring/contracts/graph-change",
            "substancedesigner://authoring/contracts/operation-safety",
        ]
    return [
        "substancedesigner://authoring/contracts/reference-first-policy",
        "substancedesigner://authoring/contracts/graph-change",
        "substancedesigner://authoring/contracts/operation-safety",
    ]


def _graph_next_tools(graph_ref: Dict[str, Any], *, include_replace: bool = True) -> list[Dict[str, Any]]:
    tools = [
        *reference_next_tools(_graph_ref_reference_uris(graph_ref)),
        tool_hint("get_authoring_capabilities", {"graph_ref": graph_ref}),
    ]
    if include_replace and graph_ref.get("kind") in {"node_property_graph", "fx_map_graph"}:
        tools.append(
            tool_hint(
                "replace_graph_state",
                {"graph_ref": graph_ref, "state": "<complete_graph_state>", "expected_current_hash": "<state_hash>"},
            )
        )
    return tools


def _post_apply_next_tools(graph_ref: Dict[str, Any]) -> list[Dict[str, Any]]:
    next_tools = [tool_hint("get_graph", {"graph_ref": graph_ref})]
    if graph_ref.get("kind") in {"node_property_graph", "fx_map_graph"} and graph_ref.get("owner_node_id"):
        next_tools.append(tool_hint("get_node", {"node_id": graph_ref["owner_node_id"]}))
        next_tools.append(tool_hint("get_preview", {"node_id": graph_ref["owner_node_id"]}))
    if graph_ref.get("kind") == "package_graph" and graph_ref.get("graph_identifier"):
        next_tools.append(tool_hint("get_preview", {"graph_identifier": graph_ref["graph_identifier"]}))
    return next_tools


def _target_to_node_property_graph_ref(target: Dict[str, Any]) -> Dict[str, Any] | None:
    node_id = target.get("node_id")
    property_id = target.get("property") or target.get("property_id")
    if node_id is None or property_id is None:
        return None
    return {
        "kind": "node_property_graph",
        "owner_node_id": str(node_id),
        "property_id": str(property_id),
        **_compact({"parent_graph": target.get("graph_identifier")}),
        "graph_type": "SDSBSFunctionGraph",
    }


def _property_graph_parameter_patch(change: Dict[str, Any]) -> bool:
    if change.get("output") is not None or _dict_items(change.get("connections")):
        return False
    nodes = _dict_items(change.get("nodes"))
    if not nodes:
        return False
    return all(isinstance(node.get("parameters"), dict) and node.get("parameters") for node in nodes)


def _parameter_patch_change(change: Dict[str, Any]) -> Dict[str, Any]:
    operations = []
    for node in _dict_items(change.get("nodes")):
        operation = {
            "op": "ensure_node",
            "id": _required_text(node.get("id"), "change.nodes[].id"),
            "parameters": node.get("parameters"),
        }
        definition = _optional_text(node.get("definition"), "change.nodes[].definition")
        if definition:
            operation["definition"] = definition
        operations.append(operation)
    return {"operations": operations}


def _graph_change_patch(change: Dict[str, Any]) -> Dict[str, Any]:
    operations: list[Dict[str, Any]] = []
    definitions_by_node = _patch_definitions_by_node(change)
    used_ids = {
        node_id
        for node_id in (
            _optional_text(node.get("id"), "change.nodes[].id") for node in _dict_items(change.get("nodes"))
        )
        if node_id
    }
    for node in _dict_items(change.get("nodes")):
        node_id = _required_text(node.get("id"), "change.nodes[].id")
        definition = _optional_text(node.get("definition"), "change.nodes[].definition")
        definition_info = definitions_by_node.get(node_id)
        host_creation = _patch_host_creation_for_definition(definition)
        parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else None
        lowered_parameters, parameter_nodes, parameter_connections = _lower_connectable_input_parameters(
            node_id=node_id,
            definition=definition_info,
            parameters=parameters,
            host_creation=host_creation,
        )
        operation: Dict[str, Any] = {
            "op": "ensure_node",
            "id": node_id,
        }
        if definition:
            operation["definition"] = definition
        if lowered_parameters:
            operation["parameters"] = lowered_parameters
        if "position" in node:
            operation["position"] = node["position"]
        if host_creation:
            operation["host_creation"] = host_creation
        operations.append(operation)
        operations.extend(parameter_nodes)
        operations.extend(parameter_connections)
    for connection in _dict_items(change.get("connections")):
        source, source_output = _graph_change_connection_endpoint(connection, "from")
        target, target_input = _graph_change_connection_endpoint(connection, "to")
        builtin_getter = _readable_variable_getter_operation(source, used_ids)
        source_is_builtin = _graph_change_connection_is_builtin(connection, source)
        if builtin_getter is not None:
            operations.append(builtin_getter)
            source = str(builtin_getter["id"])
            source_output = "unique_filter_output"
            source_is_builtin = False
        operation = {
            "op": "ensure_connection",
            "from": {"builtin": source} if source_is_builtin else source,
            "to": target,
        }
        if source_output is not None:
            operation["from_output"] = _patch_canonical_port(
                definitions_by_node.get(source or ""), "outputs", source_output
            )
        if target_input is not None:
            operation["to_input"] = _patch_canonical_port(definitions_by_node.get(target or ""), "inputs", target_input)
        operations.append(operation)
    output = _graph_change_output_node_id(change.get("output"))
    if output:
        operations.append({"op": "set_output", "node": output})
    return {"operations": operations}


def _readable_variable_getter_operation(source: str | None, used_ids: set[str]) -> Dict[str, Any] | None:
    if source not in {"shape.id", "shape.amount"}:
        return None
    base = str(source).replace(".", "_")
    node_id = _unique_lowered_parameter_node_id(base, "value", used_ids)
    return {
        "op": "ensure_node",
        "id": node_id,
        "definition": "sbs::function::get_integer1",
        "parameters": {"__constant__": source},
    }


def _lower_connectable_input_parameters(
    *,
    node_id: str,
    definition: Dict[str, Any] | None,
    parameters: Dict[str, Any] | None,
    host_creation: Dict[str, Any] | None,
) -> tuple[Dict[str, Any] | None, list[Dict[str, Any]], list[Dict[str, Any]]]:
    if not parameters or not host_creation or not isinstance(definition, dict):
        return parameters, [], []
    lowered_parameters: Dict[str, Any] = {}
    parameter_nodes: list[Dict[str, Any]] = []
    parameter_connections: list[Dict[str, Any]] = []
    used_ids = {node_id}
    for parameter_id, value in parameters.items():
        port = _patch_input_port(definition, parameter_id)
        constant_definition = _constant_definition_for_port(port)
        if port is None or constant_definition is None:
            lowered_parameters[parameter_id] = value
            continue
        const_id = _unique_lowered_parameter_node_id(node_id, str(port["id"]), used_ids)
        parameter_nodes.append(
            {
                "op": "ensure_node",
                "id": const_id,
                "definition": constant_definition,
                "parameters": {"__constant__": _parameter_literal_value(value)},
            }
        )
        parameter_connections.append(
            {
                "op": "ensure_connection",
                "from": const_id,
                "to": node_id,
                "from_output": "unique_filter_output",
                "to_input": str(port["id"]),
            }
        )
    return lowered_parameters or None, parameter_nodes, parameter_connections


def _patch_input_port(definition: Dict[str, Any], port_id: str) -> Dict[str, Any] | None:
    ports = definition.get("ports") if isinstance(definition.get("ports"), dict) else {}
    inputs = ports.get("inputs")
    if isinstance(inputs, dict):
        for canonical, port in inputs.items():
            if not isinstance(port, dict):
                continue
            aliases = [alias for alias in port.get("aliases", []) if isinstance(alias, str)]
            if port_id == canonical or port_id == port.get("id") or port_id in aliases:
                return {"id": str(canonical), **port}
        return None
    for port in _dict_items(inputs):
        canonical = _optional_text(port.get("id"), "port.id")
        if not canonical:
            continue
        aliases = [alias for alias in port.get("aliases", []) if isinstance(alias, str)]
        if port_id == canonical or port_id in aliases:
            return port
    return None


def _constant_definition_for_port(port: Dict[str, Any] | None) -> str | None:
    if not isinstance(port, dict) or port.get("connectable") is False:
        return None
    port_type = port.get("type")
    if isinstance(port_type, list):
        port_type = port_type[0] if port_type else None
    return {
        "float": "sbs::function::const_float1",
        "float1": "sbs::function::const_float1",
        "float2": "sbs::function::const_float2",
        "float3": "sbs::function::const_float3",
        "float4": "sbs::function::const_float4",
        "int": "sbs::function::const_int1",
        "int1": "sbs::function::const_int1",
        "int2": "sbs::function::const_int2",
        "int3": "sbs::function::const_int3",
        "int4": "sbs::function::const_int4",
    }.get(str(port_type or ""))


def _parameter_literal_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _unique_lowered_parameter_node_id(node_id: str, parameter_id: str, used_ids: set[str]) -> str:
    base = "{}__{}".format(node_id, re.sub(r"[^A-Za-z0-9_]+", "_", parameter_id).strip("_") or "parameter")
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _graph_change_connection_is_builtin(connection: Dict[str, Any], source: str | None) -> bool:
    endpoint = connection.get("from")
    if isinstance(endpoint, dict) and _optional_text(endpoint.get("builtin"), "change.connections[].from.builtin"):
        return True
    return bool(source and source.startswith("$"))


def _patch_definitions_by_node(change: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for node in _dict_items(change.get("nodes")):
        node_id = _optional_text(node.get("id"), "change.nodes[].id")
        definition = _optional_text(node.get("definition"), "change.nodes[].definition")
        if not node_id or not definition:
            continue
        matches = node_definitions_by_id(definition)
        if matches:
            result[node_id] = matches[0]
    return result


def _patch_canonical_port(definition: Dict[str, Any] | None, direction: str, port_id: Any) -> Any:
    if not isinstance(port_id, str) or not isinstance(definition, dict):
        return port_id
    aliases = _patch_port_aliases(definition, direction)
    return aliases.get(port_id, port_id)


def _patch_port_aliases(definition: Dict[str, Any], direction: str) -> Dict[str, str]:
    ports = definition.get("ports") if isinstance(definition.get("ports"), dict) else {}
    values = ports.get(direction)
    aliases: Dict[str, str] = {}
    if isinstance(values, dict):
        iterable = [{"id": key, **value} if isinstance(value, dict) else {"id": key} for key, value in values.items()]
    else:
        iterable = _dict_items(values)
    for port in iterable:
        canonical = _optional_text(port.get("id"), "port.id")
        if not canonical:
            continue
        aliases[canonical] = canonical
        for alias in port.get("aliases", []) if isinstance(port.get("aliases"), list) else []:
            if isinstance(alias, str) and alias:
                aliases[alias] = canonical
    return aliases


def _explicit_full_replace(change: Dict[str, Any]) -> bool:
    return change.get("replace_all") is True or _optional_text(change.get("kind"), "change.kind") in {
        "full_state",
        "replace_all",
    }


def _graph_change_output_node_id(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _optional_text(value.get("node") or value.get("id"), "change.output.node")
    return None


def _patch_host_creation_for_definition(definition: str | None) -> Dict[str, Any] | None:
    if not definition:
        return None
    creation = _creation_contract_for_definition(definition)
    if creation.get("method") != "create_instance_node":
        return None
    resource_url = _optional_text(creation.get("resource_url"), "creation.resource_url")
    if not resource_url:
        return None
    return {
        "kind": "function_graph_resource_instance",
        "resource_url": resource_url,
        **_compact(
            {
                "package_hint": creation.get("package"),
                "creation": creation,
            }
        ),
    }


def _parameter_results_for_operations(operations: list[Dict[str, Any]]) -> Dict[str, Any]:
    applied = []
    for operation in operations:
        node_id = _optional_text(operation.get("id") or operation.get("node"), "operation.node")
        if not node_id:
            continue
        definition = _optional_text(operation.get("definition"), "operation.definition")
        for parameter_id, parameter in _parameter_items(operation.get("parameters")):
            value, value_type = _parameter_value_and_type(parameter, definition=definition, parameter_id=parameter_id)
            applied.append(
                {
                    "node": node_id,
                    "parameter": parameter_id,
                    "value": value,
                    "value_type": value_type,
                }
            )
    return {"applied": applied, "skipped": [], "errors": []}


def _parameter_results_for_nodes(nodes: list[Dict[str, Any]], *, node_map: Dict[str, str]) -> Dict[str, Any]:
    operations = []
    for node in nodes:
        logical_id = _optional_text(node.get("id"), "node.id")
        if not logical_id:
            continue
        operations.append(
            {
                "id": node_map.get(logical_id, logical_id),
                "definition": node.get("definition"),
                "parameters": node.get("parameters"),
            }
        )
    return _parameter_results_for_operations(operations)


def _compact_apply_graph_change_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return an MCP-facing apply result without echoing the full requested graph change."""
    compact = {key: value for key, value in raw.items() if key not in {"patch", "state", "operations", "result"}}
    if isinstance(raw.get("result"), dict):
        compact["result"] = _compact_apply_host_result(raw["result"])
    validation = raw.get("validation")
    if isinstance(validation, dict):
        compact["validation"] = _compact_validation_result(validation)
        change = validation.get("change")
    else:
        change = None
    node_map = raw.get("node_map") if isinstance(raw.get("node_map"), dict) else {}
    if node_map:
        compact["created"] = {
            str(created["id"]): str(created["node_id"])
            for created in _dict_items(raw.get("created_nodes"))
            if created.get("id") and created.get("node_id")
        }
        compact["created_nodes"] = [_compact_created_node_summary(created) for created in _dict_items(raw.get("created_nodes"))]
    if isinstance(change, dict):
        compact["connections"] = _compact_connection_summaries(change, node_map)
        compact["updated_outputs"] = _updated_outputs_from_change(change)
    compact["updated_nodes"] = _updated_nodes_from_parameter_results(raw.get("parameter_results"))
    return compact


def _compact_apply_host_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"patch", "state", "operations"}}


def _compact_created_node_summary(created: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": created.get("id"),
        "node_id": created.get("node_id"),
        "definition": created.get("definition"),
        **_compact({"resource_url": created.get("resource_url")}),
    }


def _compact_connection_summaries(change: Dict[str, Any], node_map: Dict[str, Any]) -> list[Dict[str, Any]]:
    summaries = []
    for connection in _dict_items(change.get("connections")):
        source, source_output = _graph_change_connection_endpoint(connection, "from")
        target, target_input = _graph_change_connection_endpoint(connection, "to")
        summaries.append(
            {
                "from": {"node": source, "node_id": node_map.get(source, source), "output": source_output},
                "to": {"node": target, "node_id": node_map.get(target, target), "input": target_input},
            }
        )
    for operation in _dict_items(change.get("operations")):
        if _optional_text(operation.get("op"), "operation.op") != "ensure_connection":
            continue
        source, source_output = _graph_change_connection_endpoint(operation, "from")
        target, target_input = _graph_change_connection_endpoint(operation, "to")
        summaries.append(
            {
                "from": {"node": source, "node_id": node_map.get(source, source), "output": source_output},
                "to": {"node": target, "node_id": node_map.get(target, target), "input": target_input},
            }
        )
    return summaries


def _updated_nodes_from_parameter_results(parameter_results: Any) -> list[str]:
    if not isinstance(parameter_results, dict):
        return []
    nodes = []
    for item in _dict_items(parameter_results.get("applied")):
        node = _optional_text(item.get("node"), "parameter_result.node")
        if node:
            nodes.append(node)
    return _dedupe_texts(nodes)


def _updated_outputs_from_change(change: Dict[str, Any]) -> list[str]:
    outputs = []
    output_node = _graph_change_output_node_id(change.get("output"))
    if output_node:
        outputs.append(output_node)
    for operation in _dict_items(change.get("operations")):
        if _optional_text(operation.get("op"), "operation.op") == "set_output":
            node = _optional_text(operation.get("node"), "operation.node")
            if node:
                outputs.append(node)
    return _dedupe_texts(outputs)


def _dedupe_texts(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _compact_validation_result(validation: Dict[str, Any]) -> Dict[str, Any]:
    compact = {key: value for key, value in validation.items() if key not in {"change", "capabilities", "next_tools"}}
    compact["change_summary"] = _change_summary(validation.get("change"))
    next_tools = []
    for item in _dict_items(validation.get("next_tools")):
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        next_tools.append(
            {
                **{key: value for key, value in item.items() if key != "args"},
                "args": {key: value for key, value in args.items() if key != "change"},
            }
        )
    compact["next_tools"] = next_tools
    return compact


def _change_summary(change: Any) -> Dict[str, Any]:
    if not isinstance(change, dict):
        return {
            "operation_count": 0,
            "node_count": 0,
            "connection_count": 0,
            "sets_output": False,
            "full_replace_requested": False,
        }
    return {
        "operation_count": len(_dict_items(change.get("operations"))),
        "node_count": len(_dict_items(change.get("nodes"))),
        "connection_count": len(_dict_items(change.get("connections"))),
        "sets_output": "output" in change
        or any(
            _optional_text(operation.get("op"), "operation.op") == "set_output"
            for operation in _dict_items(change.get("operations"))
        ),
        "full_replace_requested": _explicit_full_replace(change),
    }


def _execution_trace(operation: str) -> Dict[str, Any]:
    return {
        "operation": operation,
        "callable": False,
        "public_replacement": public_tool_action_id("apply_graph_change"),
    }


def _failed_execution_trace(step: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
    return {
        **_execution_trace(str(step.get("operation") or "unknown")),
        "status": "failed",
        **{key: value for key, value in step.items() if key != "operation"},
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }


def _diagnostic_public_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    command_registry = raw.get("command_registry")
    command_count = len(command_registry) if isinstance(command_registry, list) else 0
    action_ids = public_tool_action_ids()
    public = {key: value for key, value in raw.items() if key != "command_registry"}
    public["internal_command_count"] = command_count
    public["public_tool_surface"] = {
        "complete": True,
        "count": len(action_ids),
        "tools": [
            {"public_name": name, "exposed_name": name, "tool": action_id}
            for name, action_id in action_ids.items()
        ],
        "orientation_tools": [
            {
                "public_name": name,
                "exposed_name": name,
                "tool": action_ids[name],
            }
            for name in (
                "get_graph",
                "get_node",
                "get_preview",
            )
        ],
        "planning_tools": [
            {
                "public_name": name,
                "exposed_name": name,
                "tool": action_ids[name],
            }
            for name in ("get_authoring_plan",)
        ],
        "later_phase_tools": [
            {
                "public_name": name,
                "exposed_name": name,
                "tool": action_ids[name],
            }
            for name in (
                "validate_graph_change",
                "apply_graph_change",
                "get_authoring_capabilities",
            )
        ],
    }
    public["public_mutation_tools"] = [
        action_ids["apply_graph_change"],
        action_ids["replace_graph_state"],
    ]
    public["tool_surface_note"] = (
        "Bridge command registry entries are internal implementation commands; use public MCP action ids."
    )
    return public


def _sanitize_bridge_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize_bridge_payload(item) for item in value]
    if not isinstance(value, dict):
        return value
    sanitized = {key: _sanitize_bridge_payload(item) for key, item in value.items() if key != "next_tools"}
    if "next_tools" in value:
        sanitized["internal_next_tools_omitted"] = True
    return sanitized


def _execute_python_operation(raw: Any, include_raw: bool) -> Dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {"python_result": raw}
    python_result = payload.get("result") if "result" in payload else payload.get("python_result")
    normalized = {
        "operation": "execute_python",
        "ok": payload.get("status") != "error",
        "status": payload.get("status"),
        "executed": bool(payload.get("executed")),
        "python_result": python_result,
        "stdout": payload.get("stdout", ""),
        "stderr": payload.get("stderr", ""),
        "execution_message": payload.get("message", ""),
        "traceback": payload.get("traceback", ""),
    }
    return _with_raw(normalized, raw, include_raw)


def _preview_operation(raw: Any, include_raw: bool) -> Dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise SubstanceDesignerBridgeError("get_preview returned no preview payload")
    if raw.get("status") == "error" or raw.get("error"):
        normalized = normalize_operation_result("get_preview", raw)
        normalized["ok"] = False
        result = normalized["result"]
        if isinstance(result, dict):
            result.setdefault("diagnostics", [])
            result.setdefault("diagnostics_available", bool(result.get("diagnostics")))
        return _with_raw(normalized, raw, include_raw)
    image_path = raw.get("image_path")
    if not isinstance(image_path, str) or not image_path.strip():
        raise SubstanceDesignerBridgeError("get_preview returned no image_path")
    normalized = normalize_operation_result("get_preview", raw)
    result = normalized.get("result")
    if isinstance(result, dict):
        result["preview_contract"] = _preview_contract()
    return _with_raw(normalized, raw, include_raw)


ENUM_PARAMETER_OPTIONS: dict[tuple[str, str], list[Dict[str, Any]]] = {
    ("sbs::library::3d_viewer", "scene_type"): [
        {"value": 0, "label": "SDF"},
        {"value": 1, "label": "Intersection"},
    ],
    ("sbs::library::3d_viewer", "output"): [
        {"value": 0, "label": "Beauty"},
        {"value": 1, "label": "Normal WS"},
        {"value": 2, "label": "Normal TS"},
        {"value": 3, "label": "Position"},
        {"value": 4, "label": "Distance"},
        {"value": 5, "label": "Depth"},
        {"value": 6, "label": "Color"},
        {"value": 7, "label": "Material ID"},
        {"value": 8, "label": "Sphere tracing steps"},
        {"value": 9, "label": "Custom"},
    ],
    ("sbs::library::shape_splatter_v2", "shape_type"): [
        {"value": 1, "label": "SDF Function"},
        {"value": 2, "label": "Cube"},
        {"value": 3, "label": "Sphere"},
        {"value": 4, "label": "Cylinder"},
        {"value": 10, "label": "Plane"},
        {"value": 11, "label": "Disc"},
        {"value": 12, "label": "Image input"},
        {"value": 13, "label": "Grid atlas"},
    ],
}


def _enrich_node_parameter_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    definition = _node_authoring_definition(node)
    if not definition:
        return node
    for container_key in ("inputs", "annotations", "parameters"):
        _attach_enum_metadata(node.get(container_key), definition)
    return node


def _enrich_node_definition_identity(node: Dict[str, Any]) -> Dict[str, Any]:
    runtime_definition = _optional_text(node.get("definition"), "node.definition")
    resolved = _resolve_instance_authoring_definition(node)
    if not resolved:
        return node
    return {
        **node,
        "runtime_definition": runtime_definition,
        "resolved_definition": resolved["definition"],
        "definition_evidence": resolved["evidence"],
    }


def _resolve_instance_authoring_definition(node: Dict[str, Any]) -> Dict[str, Any] | None:
    definition = _optional_text(node.get("definition"), "node.definition")
    if not _definition_needs_instance_resolution(definition):
        return None
    resource_url = _instance_resource_url(node)
    if not resource_url:
        return None
    normalized_resource_url = _resource_url_identity(resource_url)
    for candidate in node_definitions():
        creation = candidate.get("creation") if isinstance(candidate.get("creation"), dict) else {}
        candidate_url = _optional_text(creation.get("resource_url"), "creation.resource_url")
        if candidate_url and _resource_url_identity(candidate_url) == normalized_resource_url:
            definition_id = _optional_text(candidate.get("definition_id"), "candidate.definition_id")
            if definition_id:
                return {
                    "definition": definition_id,
                    "evidence": {
                        "source": "instance_resource_url",
                        "resource_url": resource_url,
                    },
                }
    return None


def _instance_resource_url(node: Dict[str, Any]) -> str | None:
    instance = node.get("instance") if isinstance(node.get("instance"), dict) else {}
    for value in (
        instance.get("resource_url"),
        instance.get("resourceUrl"),
        node.get("resource_url"),
        node.get("resourceUrl"),
    ):
        text = _optional_text(value, "resource_url")
        if text:
            return text
    return None


def _resource_url_identity(value: str) -> str:
    text = value.strip()
    text = text.split("?", 1)[0]
    return text.rstrip("/").lower()


def _definition_needs_instance_resolution(definition: str | None) -> bool:
    return definition in {None, "", "sbs::compositing::sbscompgraph_instance"}


def _node_authoring_definition(node: Dict[str, Any]) -> str | None:
    return _optional_text(
        node.get("resolved_definition") or node.get("definition"),
        "node.definition",
    )


def _attach_enum_metadata(value: Any, definition: str) -> None:
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, dict):
            continue
        parameter_id = _optional_text(item.get("id") or item.get("identifier"), "parameter.id")
        if not parameter_id:
            continue
        options = _enum_options_for_parameter(definition, parameter_id)
        if not options:
            continue
        item["enum_options"] = [dict(option) for option in options]
        current = item.get("value", item.get("current_value"))
        current_label = _enum_label(options, current)
        if current_label is not None:
            item["current_label"] = current_label


def _enum_label(options: list[Dict[str, Any]], value: Any) -> str | None:
    try:
        current = int(value)
    except (TypeError, ValueError):
        return None
    for option in options:
        if option.get("value") == current:
            label = option.get("label")
            return str(label) if label is not None else None
    return None


def _enum_options_for_parameter(definition: str, parameter_id: str) -> list[Dict[str, Any]] | None:
    for node in node_definitions_by_id(definition):
        for parameter in _dict_items(node.get("parameters")):
            if parameter.get("id") != parameter_id:
                continue
            enum = parameter.get("enum")
            if isinstance(enum, dict) and isinstance(enum.get("options"), list):
                return [dict(option) for option in enum["options"] if isinstance(option, dict)]
    return ENUM_PARAMETER_OPTIONS.get((definition, parameter_id))


def _enrich_node_with_editable_property_graphs(node: Dict[str, Any], *, graph_identifier: str | None) -> Dict[str, Any]:
    node_id = _optional_text(node.get("node_id"), "node.node_id")
    definition = _node_authoring_definition(node)
    if not node_id or not definition:
        return node
    existing_refs_by_property = {
        str(ref.get("property") or ref.get("property_id")): ref
        for ref in node.get("nested_graph_refs", [])
        if isinstance(ref, dict) and (ref.get("property") or ref.get("property_id"))
    }
    editable_graphs = []
    for contract in _function_contracts_for_owner(definition):
        property_id = _required_text(contract.get("property_id"), "contract.property_id")
        graph_ref = {
            "kind": "node_property_graph",
            **_compact({"parent_graph": graph_identifier}),
            "owner_node_id": node_id,
            "owner_definition": definition,
            "property_id": property_id,
            "graph_type": contract.get("graph_type") or "SDSBSFunctionGraph",
        }
        existing = existing_refs_by_property.get(property_id)
        exists = bool(existing.get("exists", True)) if isinstance(existing, dict) else False
        graph_context = resolve_graph_context(graph_ref=graph_ref, context=None)
        contract_payload = dict(graph_context["contract"])
        if contract_payload.get("kind") == "value_processor":
            output = dict(contract_payload.get("output") if isinstance(contract_payload.get("output"), dict) else {})
            resolved_type = _value_processor_resolved_output_type(node)
            if resolved_type:
                output["resolved_type"] = resolved_type
                contract_payload["output"] = output
                contract_payload["confidence"] = "medium"
        workflow_uri = SDF_FUNCTION_WORKFLOW_URI if contract_payload.get("kind") == "sdf_function" else None
        read_tool = tool_hint("get_graph", {"graph_ref": graph_ref})
        capabilities_tool = tool_hint("get_authoring_capabilities", {"graph_ref": graph_ref})
        entry = {
            "property_id": property_id,
            "label": _property_label(node, property_id),
            "graph_ref": graph_ref,
            "exists": exists,
            "apply_support": _editable_graph_apply_support(exists),
            "graph_type": graph_ref["graph_type"],
            "contract_kind": contract_payload.get("kind"),
            "contract": contract_payload,
            "output_contract": contract_payload.get("output")
            if isinstance(contract_payload.get("output"), dict)
            else {},
            "builtins": contract_payload.get("builtins", {}),
            **_compact({"workflow_uri": workflow_uri}),
            "preview_targets": _editable_graph_preview_targets(definition, node_id, property_id),
            "read_tool": read_tool,
            "capabilities_tool": capabilities_tool,
            "next_tools": [read_tool, capabilities_tool],
        }
        editable_graphs.append(entry)
        _attach_property_graph_to_ports(node.get("inputs"), property_id, entry)
        _attach_property_graph_to_ports(node.get("annotations"), property_id, entry)
    if not editable_graphs:
        return node
    merged_refs = _merge_nested_graph_refs(node.get("nested_graph_refs"), editable_graphs)
    graph_ref_shortcuts = _editable_graph_ref_shortcuts(editable_graphs)
    return {
        **node,
        "editable_property_graphs": editable_graphs,
        "graph_surfaces": editable_graphs,
        **graph_ref_shortcuts,
        "nested_graph_refs": merged_refs,
    }


def _property_label(node: Dict[str, Any], property_id: str) -> str | None:
    for container_key in ("inputs", "annotations", "parameters"):
        for item in node.get(container_key, []) if isinstance(node.get(container_key), list) else []:
            if isinstance(item, dict) and item.get("id") == property_id:
                label = item.get("label") or item.get("display_name")
                return str(label) if label is not None else None
    return None


def _editable_graph_preview_targets(definition: str, node_id: str, property_id: str) -> list[Dict[str, Any]]:
    if definition == "sbs::library::3d_viewer" and property_id == "sdf_scene":
        return [
            {
                "node_id": node_id,
                "node_output_id": "output",
                "purpose": "preview SDF function silhouette before downstream composition",
            }
        ]
    if definition == "sbs::library::shape_splatter_v2" and property_id == "pattern_sdf_function":
        return [
            {
                "node_id": node_id,
                "node_output_id": "sdf_color",
                "purpose": "verify SDF contribution is readable in Shape Splatter output",
            },
            {
                "node_id": node_id,
                "node_output_id": "height",
                "purpose": "verify scattered SDF height contribution before material composition",
            },
        ]
    return []


def _function_contracts_for_owner(definition: str) -> list[Dict[str, Any]]:
    registry = load_function_contract_registry()
    contracts = registry.get("function_contracts")
    if not isinstance(contracts, dict):
        return []
    result = []
    for value in contracts.values():
        if isinstance(value, dict) and value.get("owner_definition_id") == definition and value.get("property_id"):
            result.append(dict(value))
    return sorted(result, key=_function_contract_sort_key)


def _function_contract_sort_key(contract: Dict[str, Any]) -> tuple[int, str]:
    kind = str(contract.get("kind") or "")
    property_id = str(contract.get("property_id") or "")
    return (0 if kind == "sdf_function" else 1, property_id)


def _attach_property_graph_to_ports(value: Any, property_id: str, entry: Dict[str, Any]) -> None:
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, dict) and item.get("id") == property_id:
            item["role"] = "function_graph_property"
            item["graph_ref"] = entry["graph_ref"]
            item["contract_kind"] = entry["contract"].get("kind")
            item["exists"] = entry["exists"]


def _merge_nested_graph_refs(value: Any, editable_graphs: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    refs = [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    seen = {str(ref.get("property") or ref.get("property_id")) for ref in refs}
    for graph in editable_graphs:
        property_id = str(graph["property_id"])
        if property_id in seen:
            continue
        refs.append(
            {
                "property": property_id,
                "property_id": property_id,
                "graph_type": graph["graph_type"],
                "exists": graph["exists"],
                "apply_support": graph["apply_support"],
                "contract_kind": graph["contract_kind"],
                **_compact({"workflow_uri": graph.get("workflow_uri")}),
                "graph_ref": graph["graph_ref"],
                "read_tool": graph["read_tool"],
            }
        )
    return refs


def _editable_graph_ref_shortcuts(editable_graphs: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Return compact top-level graph-ref shortcuts for ordinary get_node display."""
    refs = []
    sdf_graph_ref = None
    for graph in editable_graphs:
        graph_ref = graph.get("graph_ref") if isinstance(graph.get("graph_ref"), dict) else None
        property_id = _optional_text(graph.get("property_id"), "editable_graph.property_id")
        if graph_ref is None or not property_id:
            continue
        refs.append(
            {
                "property_id": property_id,
                "contract_kind": graph.get("contract_kind"),
                "exists": bool(graph.get("exists")),
                "apply_support": graph.get("apply_support"),
                "graph_ref": graph_ref,
            }
        )
        if graph.get("contract_kind") == "sdf_function" and sdf_graph_ref is None:
            sdf_graph_ref = graph_ref
    return {
        "editable_graph_refs": refs,
        **_compact({"sdf_graph_ref": sdf_graph_ref}),
    }


def _editable_graph_apply_support(exists: bool) -> Dict[str, Any]:
    return {
        "patch": {"supported": True, "omitted_means": "preserve"},
        "create_if_missing": {
            "supported": True,
            "strategy": "patch_graph_ref",
            "host_strategy_hidden": True,
        }
        if not exists
        else {"supported": False, "reason": "graph already exists"},
        "replace_full_state": {
            "supported": False,
            "reason": "full replacement is not part of apply_graph_change",
        },
    }


def _value_processor_resolved_output_type(node: Dict[str, Any]) -> str | None:
    for port in node.get("inputs", []) if isinstance(node.get("inputs"), list) else []:
        if not isinstance(port, dict) or port.get("id") not in {"outputtype", "output_type", "type"}:
            continue
        value = port.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = _optional_text(value.get("value") or value.get("id") or value.get("name"), "outputtype.value")
            if text:
                return text
    return None


def _preview_contract() -> Dict[str, Any]:
    return {
        "node_output": {
            "use_when": "Previewing a node output image.",
            "dimension_fields": ["resolution"],
            "invalid_fields": ["width", "height"],
        },
        "graph_3d_view": {
            "use_when": "Capturing the graph 3D View with no node_id.",
            "dimension_fields": ["resolution", "width", "height"],
            "requires": ["graph_identifier or current graph"],
        },
    }


def _compact(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _dict_items(value: JsonValue) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _parameter_items(value: JsonValue) -> list[tuple[str, JsonValue]]:
    if not isinstance(value, dict):
        return []
    return [(str(key), item) for key, item in value.items() if str(key).strip()]


def _graph_change_parameter_items(node: GraphChangeNode) -> GraphChangeParameterItems:
    items = _parameter_items(node.get("parameters"))
    definition = node.get("definition")
    if definition != "sbs::compositing::output":
        return items
    return [
        (_output_node_parameter_id(parameter_id), _output_node_parameter_value(parameter_id, parameter))
        for parameter_id, parameter in items
    ]


def _output_node_parameter_id(parameter_id: str) -> str:
    return "usages" if parameter_id == "usage" else parameter_id


def _output_node_parameter_value(
    parameter_id: str, parameter: GraphChangeParameterValue
) -> GraphChangeParameterValue | LoweredGraphChangeParameter:
    if parameter_id not in {"identifier", "label", "usage", "usages"}:
        return parameter
    if parameter_id in {"usage", "usages"}:
        if isinstance(parameter, dict) and "value" in parameter:
            return {"value": parameter.get("value"), "value_type": "usage_array"}
        return {"value": parameter, "value_type": "usage_array"}
    if isinstance(parameter, dict) and "value" in parameter:
        return {"value": parameter.get("value"), "value_type": "string"}
    return {"value": parameter, "value_type": "string"}


def _graph_change_connection_endpoint(
    connection: GraphChangeConnection, side: str
) -> tuple[str, OptionalReferenceInput]:
    endpoint = connection.get(side)
    if isinstance(endpoint, dict):
        node_id = _connection_endpoint_node(endpoint, f"change.connections[].{side}.node")
        port = _connection_endpoint_port(endpoint, side)
        return node_id, port
    if side == "from":
        port = _reference_input(connection.get("from_output") or connection.get("output"))
    else:
        port = _reference_input(connection.get("to_input") or connection.get("input"))
    return _required_text(endpoint, f"change.connections[].{side}"), port


def _canonical_graph_change_connections(value: JsonValue) -> list[Dict[str, Any]]:
    result = []
    for connection in _dict_items(value):
        source_node, source_port = _graph_change_connection_endpoint(connection, "from")
        target_node, target_port = _graph_change_connection_endpoint(connection, "to")
        result.append(
            {
                "from": {"node": source_node, "output": source_port or "unique_filter_output"},
                "to": {"node": target_node, "input": target_port},
            }
        )
    return result


def _filter_graph_change_nodes(
    value: JsonValue, node_ids: set[str] | None, bounds: Dict[str, float] | None
) -> list[Dict[str, Any]]:
    nodes = _dict_items(value)
    if node_ids is None and bounds is None:
        return nodes
    return [
        node
        for node in nodes
        if (node_ids is None or _graph_change_node_id(node) in node_ids)
        and (bounds is None or _node_position_in_bounds(node, bounds))
    ]


def _filter_graph_change_connections(value: JsonValue, node_ids: set[str] | None) -> list[Dict[str, Any]]:
    connections = _dict_items(value)
    if node_ids is None:
        return connections
    result = []
    for connection in connections:
        source = _optional_connection_node(connection, "from")
        target = _optional_connection_node(connection, "to")
        if connection.get("from_builtin") and target in node_ids:
            result.append(connection)
            continue
        if source in node_ids and target in node_ids:
            result.append(connection)
    return result


def _filter_package_graph_state(
    state: Dict[str, Any], node_ids: set[str] | None, bounds: Dict[str, float] | None
) -> Dict[str, Any]:
    nodes = [
        node
        for node in _dict_items(state.get("nodes"))
        if (node_ids is None or _optional_text(node.get("identifier") or node.get("id"), "node.identifier") in node_ids)
        and (bounds is None or _node_position_in_bounds(node, bounds))
    ]
    selected_ids = {
        node_id
        for node in nodes
        if (node_id := _optional_text(node.get("identifier") or node.get("id"), "node.identifier"))
    }
    connections = [
        connection
        for connection in _dict_items(state.get("connections"))
        if _package_connection_node(connection, "from") in selected_ids
        and _package_connection_node(connection, "to") in selected_ids
    ]
    canonical_connections = [
        connection
        for connection in _dict_items(state.get("canonical_connections"))
        if _package_connection_node(connection, "from") in selected_ids
        and _package_connection_node(connection, "to") in selected_ids
    ]
    return {
        **state,
        "nodes": nodes,
        "connections": connections,
        "canonical_connections": canonical_connections,
        "returned_node_count": len(nodes),
        "connection_count": len(connections),
        **_partial_graph_view_metadata(True),
    }


def _is_partial_graph_view(node_ids: set[str] | None, bounds: Dict[str, float] | None) -> bool:
    return node_ids is not None or bounds is not None


def _partial_graph_view_metadata(partial: bool) -> Dict[str, Any]:
    if not partial:
        return {"partial_view": False, "unsafe_as_replace_input": False}
    return {
        "partial_view": True,
        "unsafe_as_replace_input": True,
        "replace_input_warning": (
            "This graph state is filtered and omits nodes or connections; use it as patch context, not as full "
            "replace state."
        ),
    }


def _graph_change_node_id(node: Dict[str, Any]) -> str | None:
    return _optional_text(node.get("id") or node.get("identifier"), "node.id")


def _selected_graph_change_node_ids(nodes: list[Dict[str, Any]]) -> set[str]:
    return {node_id for node in nodes if (node_id := _graph_change_node_id(node))}


def _node_position_in_bounds(node: Dict[str, Any], bounds: Dict[str, float]) -> bool:
    position = node.get("position")
    if not isinstance(position, list) or len(position) < 2:
        return False
    x = _number_or_none(position[0])
    y = _number_or_none(position[1])
    if x is None or y is None:
        return False
    return x >= bounds["min_x"] and x <= bounds["max_x"] and y >= bounds["min_y"] and y <= bounds["max_y"]


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _optional_connection_node(connection: Dict[str, Any], side: str) -> str | None:
    if side == "from" and connection.get("from_builtin"):
        return None
    endpoint = connection.get(side)
    if isinstance(endpoint, dict):
        node = endpoint.get("node")
        if isinstance(node, dict):
            return _optional_text(node.get("id") or node.get("node"), f"connection.{side}.node")
        return _optional_text(node or endpoint.get("id"), f"connection.{side}.node")
    return _optional_text(endpoint or connection.get(f"{side}_node"), f"connection.{side}")


def _package_connection_node(connection: Dict[str, Any], side: str) -> str | None:
    endpoint = connection.get(side)
    if isinstance(endpoint, dict):
        node = endpoint.get("node")
        if isinstance(node, dict):
            return _optional_text(node.get("id") or node.get("node"), f"connection.{side}.node")
        return _optional_text(node, f"connection.{side}.node")
    if side == "from":
        return _optional_text(connection.get("from_node") or endpoint, "connection.from")
    return _optional_text(connection.get("to_node") or endpoint, "connection.to")


def _enrich_graph_change_nodes_with_definition_ports(value: JsonValue) -> list[Dict[str, Any]]:
    nodes = _dict_items(value)
    enriched = []
    for node in nodes:
        if isinstance(node.get("ports"), dict):
            enriched.append(node)
            continue
        definition_id = _optional_text(node.get("definition"), "node.definition")
        definition = _first_node_definition(definition_id)
        if not definition:
            enriched.append(node)
            continue
        ports = _definition_ports_by_id(definition)
        ports_evidence = definition.get("ports_evidence") if isinstance(definition.get("ports_evidence"), dict) else {}
        enriched.append(
            {
                **node,
                **_compact({"ports": ports}),
                "ports_evidence": {
                    **ports_evidence,
                    "source": "definition_registry",
                },
            }
        )
    return enriched


def _definition_ports_by_id(definition: Dict[str, Any]) -> Dict[str, Any] | None:
    ports = definition.get("ports")
    if not isinstance(ports, dict):
        return None
    return {
        "inputs": _port_collection_by_id(ports.get("inputs")),
        "outputs": _port_collection_by_id(ports.get("outputs")),
    }


def _port_collection_by_id(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _normalize_port_payload(item) for key, item in value.items() if isinstance(item, dict)}
    if not isinstance(value, list):
        return {}
    result = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        port_id = item.get("id")
        if isinstance(port_id, (str, int)) and str(port_id).strip():
            result[str(port_id)] = _normalize_port_payload(
                {key: port_value for key, port_value in item.items() if key != "id"}
            )
    return result


def _normalize_port_payload(port: Dict[str, Any]) -> Dict[str, Any]:
    port_type = port.get("type")
    if isinstance(port_type, list) and len(port_type) == 1:
        return {**port, "type": port_type[0], "types": port_type}
    if isinstance(port_type, list):
        return {**port, "types": port_type}
    if isinstance(port_type, str):
        return {**port, "types": [port_type]}
    return port


def _first_node_definition(definition_id: str | None) -> Dict[str, Any] | None:
    if not definition_id:
        return None
    for definition in node_definitions_by_id(definition_id):
        if isinstance(definition, dict):
            return definition
    return None


def _connection_endpoint_node(endpoint: Dict[str, Any], name: str) -> str:
    builtin = endpoint.get("builtin")
    if isinstance(builtin, str) and builtin.strip():
        return builtin
    node = endpoint.get("node")
    if isinstance(node, dict):
        return _required_text(node.get("id") or node.get("node"), name)
    return _required_text(node or endpoint.get("id"), name)


def _connection_endpoint_port(endpoint: Dict[str, Any], side: str) -> OptionalReferenceInput:
    if side == "from":
        return _reference_input(endpoint.get("output") or endpoint.get("port") or endpoint.get("from_output"))
    return _reference_input(endpoint.get("input") or endpoint.get("port") or endpoint.get("to_input"))


def _reference_input(value: JsonValue) -> OptionalReferenceInput:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, dict)):
        return value
    return None


def _parameter_value_and_type(
    parameter: JsonValue, *, definition: str | None = None, parameter_id: str | None = None
) -> tuple[JsonValue, str]:
    if isinstance(parameter, dict) and "value" in parameter:
        value = _required_value(parameter.get("value"), "parameter.value")
        return value, _required_text(
            str(
                parameter.get("value_type")
                or parameter.get("type")
                or _static_parameter_value_type(definition, parameter_id)
                or _infer_parameter_value_type(value)
            ),
            "parameter.value_type",
        )
    value = _required_value(parameter, "parameter")
    return value, _static_parameter_value_type(definition, parameter_id) or _infer_parameter_value_type(value)


def _static_parameter_value_type(definition: str | None, parameter_id: str | None) -> str | None:
    if not definition or not parameter_id:
        return None
    for node in node_definitions_by_id(definition):
        for parameter in _dict_items(node.get("parameters")):
            if parameter.get("id") != parameter_id:
                continue
            if not isinstance(parameter.get("enum"), dict) and (definition, parameter_id) not in ENUM_PARAMETER_OPTIONS:
                return None
            parameter_types = parameter.get("type")
            if isinstance(parameter_types, list) and parameter_types:
                return str(parameter_types[0])
            if isinstance(parameter_types, str) and parameter_types:
                return parameter_types
        ports = node.get("ports") if isinstance(node.get("ports"), dict) else {}
        for port in _dict_items(ports.get("inputs")):
            if port.get("id") != parameter_id:
                continue
            port_types = port.get("type")
            if isinstance(port_types, list) and port_types:
                return str(port_types[0])
            if isinstance(port_types, str) and port_types:
                return port_types
    return None


def _infer_parameter_value_type(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        if len(value) == 2:
            return "float2"
        if len(value) == 3:
            return "float3"
        if len(value) == 4:
            return "float4"
    if isinstance(value, dict):
        keys = set(value)
        if {"r", "g", "b"}.issubset(keys):
            return "color"
        if {"x", "y", "z", "w"}.issubset(keys):
            return "float4"
        if {"x", "y", "z"}.issubset(keys):
            return "float3"
        if {"x", "y"}.issubset(keys):
            return "float2"
    return "float"


def _created_node_id(result: Dict[str, Any], *, fallback: str) -> str:
    for key in ("node_id", "identifier", "id"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    node = result.get("node")
    if isinstance(node, dict):
        return _created_node_id(node, fallback=fallback)
    return fallback


def _looks_like_existing_host_node_id(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value.strip()))


def _creation_contract_for_definition(definition_id: str) -> Dict[str, Any]:
    for node in node_definitions_by_id(definition_id):
        creation = node.get("creation")
        if isinstance(creation, dict):
            return dict(creation)
    return {"method": "create_node"}


def _package_hint_from_creation(creation: Dict[str, Any]) -> Dict[str, Any] | None:
    hint = _compact(
        {
            "package": creation.get("package"),
            "standard_package_candidates": creation.get("standard_package_candidates"),
        }
    )
    return hint or None


def _required_text(value: JsonValue, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SubstanceDesignerValidationError(f"{name} must be a non-empty string")
    return value


def _required_value(value: JsonValue, name: str) -> JsonValue:
    if value is None:
        raise SubstanceDesignerValidationError(f"{name} is required")
    return value


def _required_node_id(value: NodeIdInput, name: str) -> str:
    if isinstance(value, bool):
        raise SubstanceDesignerValidationError(f"{name} must be a non-empty string or integer")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    raise SubstanceDesignerValidationError(f"{name} must be a non-empty string or integer")


def _optional_node_id(value: OptionalNodeIdInput, name: str) -> Optional[str]:
    if value is None:
        return None
    return _required_node_id(value, name)


def _optional_node_id_set(value: list[NodeIdInput] | None) -> set[str] | None:
    if value is None:
        return None
    return {_required_node_id(item, "node_ids[]") for item in value}


def _optional_position_bounds(value: OptionalSkillObjectInput) -> Dict[str, float] | None:
    if value is None:
        return None
    bounds = _required_dict(value, "position_bounds")
    return {
        "min_x": _number(bounds.get("min_x"), "position_bounds.min_x"),
        "max_x": _number(bounds.get("max_x"), "position_bounds.max_x"),
        "min_y": _number(bounds.get("min_y"), "position_bounds.min_y"),
        "max_y": _number(bounds.get("max_y"), "position_bounds.max_y"),
    }


def _optional_text(value: str | None, name: str) -> Optional[str]:
    if value is None:
        return None
    return _required_text(value, name)


def _detail_level(value: str) -> str:
    text = _required_text(value, "detail_level")
    if text not in {"structure", "semantic", "full", "debug"}:
        raise SubstanceDesignerValidationError("detail_level must be one of: structure, semantic, full, debug")
    return text


def _resolution_preset(value: str) -> str:
    text = _required_text(value, "resolution")
    if text not in {"small", "medium", "large"}:
        raise SubstanceDesignerValidationError("resolution must be one of: small, medium, large")
    return text


def _non_negative_int(value: JsonValue, name: str) -> int:
    if value is None or isinstance(value, bool) or isinstance(value, (list, dict)):
        raise SubstanceDesignerValidationError(f"{name} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SubstanceDesignerValidationError(f"{name} must be a non-negative integer") from exc
    if number < 0:
        raise SubstanceDesignerValidationError(f"{name} must be a non-negative integer")
    return number


def _positive_int(value: JsonValue, name: str) -> int:
    number = _non_negative_int(value, name)
    if number <= 0:
        raise SubstanceDesignerValidationError(f"{name} must be a positive integer")
    return number


def _optional_positive_int(value: JsonValue, name: str) -> Optional[int]:
    if value is None:
        return None
    return _positive_int(value, name)


def _required_position(value: PositionInput, name: str) -> list[float]:
    position = _optional_position(value, name)
    if position is None:
        raise SubstanceDesignerValidationError(f"{name} must contain exactly two numbers")
    return position


def _optional_position(value: OptionalPositionInput, name: str) -> Optional[list[float]]:
    if value is None:
        return None
    if isinstance(value, dict):
        for first, second in (("x", "y"), ("left", "top"), ("width", "height"), ("0", "1")):
            if first in value and second in value:
                return [_number(value[first], f"{name}.{first}"), _number(value[second], f"{name}.{second}")]
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SubstanceDesignerValidationError(f"{name} must contain exactly two numbers")
    return [_number(value[0], f"{name}[0]"), _number(value[1], f"{name}[1]")]


def _optional_color(value: OptionalColorInput, name: str) -> Optional[list[float]]:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("rgba", "rgb", "value", "components"):
            item = value.get(key)
            if isinstance(item, (list, tuple)):
                return _optional_color(item, name)
        if all(key in value for key in ("r", "g", "b")):
            return [
                _number(value["r"], f"{name}.r"),
                _number(value["g"], f"{name}.g"),
                _number(value["b"], f"{name}.b"),
                _number(value.get("a", 1.0), f"{name}.a"),
            ]
        if all(key in value for key in ("red", "green", "blue")):
            return [
                _number(value["red"], f"{name}.red"),
                _number(value["green"], f"{name}.green"),
                _number(value["blue"], f"{name}.blue"),
                _number(value.get("alpha", 1.0), f"{name}.alpha"),
            ]
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)) or len(value) != 4:
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return [_number(value[index], f"{name}[{index}]") for index in range(3)] + [1.0]
        raise SubstanceDesignerValidationError(f"{name} must contain three or four numbers")
    return [_number(value[index], f"{name}[{index}]") for index in range(4)]


def _number(value: JsonValue, name: str) -> float:
    if value is None or isinstance(value, bool) or isinstance(value, (list, dict)):
        raise SubstanceDesignerValidationError(f"{name} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SubstanceDesignerValidationError(f"{name} must be a number") from exc


def _positive_number(value: JsonValue, name: str) -> float:
    number = _number(value, name)
    if number <= 0:
        raise SubstanceDesignerValidationError(f"{name} must be greater than 0")
    return number


def _optional_dict(value: OptionalControlTargetInput, name: str) -> OptionalControlTargetInput:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SubstanceDesignerValidationError(f"{name} must be an object")
    return value


def _optional_context(value: OptionalSkillObjectInput) -> OptionalSkillObjectInput:
    if value is None:
        return None
    if isinstance(value, str):
        return {"kind": _required_text(value, "context")}
    if not isinstance(value, dict):
        raise SubstanceDesignerValidationError("context must be an object or string")
    return value


def _required_dict(value: ControlTargetInput, name: str) -> ControlTargetInput:
    if not isinstance(value, dict):
        raise SubstanceDesignerValidationError(f"{name} must be an object")
    return value


def _list_of_dicts(value: ControlUpdatesInput, name: str) -> list[dict[str, JsonValue]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        raise SubstanceDesignerValidationError(f"{name} must be a list")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise SubstanceDesignerValidationError(f"{name}[{index}] must be an object")
        result.append(item)
    return result


def _property_ref(*values: OptionalReferenceInput) -> str:
    for value in values:
        ref = _optional_ref(value)
        if ref is not None:
            return ref
    raise SubstanceDesignerValidationError("parameter_id, property, property_id, id, or control is required")


def _optional_port_ref(value: OptionalReferenceInput, name: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "default", "*", "auto"}:
        return None
    ref = _optional_ref(value)
    if ref is None:
        raise SubstanceDesignerValidationError(f"{name} must be a string, integer, or port object")
    return ref


def _optional_ref(value: OptionalReferenceInput) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        for key in ("id", "identifier", "property", "property_id", "parameter_id", "input_id", "output_id", "port"):
            item = value.get(key)
            if isinstance(item, int) and not isinstance(item, bool):
                return str(item)
            if isinstance(item, str) and item.strip():
                return item
        source = value.get("source")
        if isinstance(source, dict):
            return _optional_ref(source)
    return None


def _node_definition_id(
    definition_id: Optional[str],
    definition: Optional[str],
    node_type: Optional[str],
    resource_url: Optional[str],
) -> str:
    raw = resource_url or definition_id or definition or node_type
    text = _required_text(raw, "definition_id")
    if text.startswith("pkg://") or "::" in text:
        return text
    return "sbs::compositing::{}".format(text)


def _resolution_log2_pair(value: ResolutionInput) -> tuple[int, int]:
    width, height = _resolution_size_pair(value)
    return _resolution_to_log2(width), _resolution_to_log2(height)


def _resolution_size_pair(value: ResolutionInput) -> tuple[int, int]:
    if isinstance(value, dict):
        width = value.get("width") or value.get("w") or value.get("x")
        height = value.get("height") or value.get("h") or value.get("y") or width
        return _positive_int(width, "width"), _positive_int(height, "height")
    if isinstance(value, int) and not isinstance(value, bool):
        size = _positive_int(value, "size")
        return size, size
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+)\s*[x,]\s*(\d+)\s*", value.lower())
        if match:
            return _positive_int(match.group(1), "width"), _positive_int(match.group(2), "height")
        size = _positive_int(value, "size")
        return size, size
    raise SubstanceDesignerValidationError("resolution must be a number, WIDTHxHEIGHT string, or width/height object")


def _resolution_to_log2(value: int) -> int:
    exponent = 0
    current = 1
    while current < value:
        current *= 2
        exponent += 1
    if current != value:
        raise SubstanceDesignerValidationError(f"resolution must be a power of two, got {value}")
    return exponent


def _merge_reference_uris(existing: Any, extra: list[str]) -> list[str]:
    uris = [uri for uri in existing if isinstance(uri, str)] if isinstance(existing, list) else []
    uris.extend(extra)
    return list(dict.fromkeys(uris))


def _client_version() -> str:
    return __version__
