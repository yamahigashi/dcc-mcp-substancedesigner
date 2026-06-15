"""Static Substance Designer graph authoring reference resources."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from importlib.resources import as_file, files
from typing import Any

from dcc_mcp_core.skills_helper import load_yaml_file

AUTHORING_SCHEME = "substancedesigner"
AUTHORING_PREFIX = "substancedesigner://authoring"
AUTHORING_MIME = "application/json"
AUTHORING_SCHEMA_VERSION = "1.0"
GET_REFERENCE_TOOL = "get_reference"
ACTION_PREFIX = "substance_designer__"
FUNCTION_CONTRACTS_URI = f"{AUTHORING_PREFIX}/registries/function-contracts"
FX_MAP_GRAPH_URI = f"{AUTHORING_PREFIX}/registries/fx-map-graph"
FUNCTION_LIVE_PROBE_RESULTS_URI = f"{AUTHORING_PREFIX}/registries/function-live-probe-results"
SDF_FUNCTION_WORKFLOW_URI = f"{AUTHORING_PREFIX}/workflows/sdf-function"
NODE_DEFINITION_KINDS = ("atomic", "library", "function-atomic", "function-library")
NODE_DEFINITION_FILES = {
    "atomic": "atomic.json",
    "library": "library.json",
    "function-atomic": "function_atomic.json",
    "function-library": "function_library.json",
}
FUNCTION_CONTRACTS_FILE = "function_contracts.json"
FX_MAP_GRAPH_FILE = "fx_map_graph.json"
FUNCTION_LIVE_PROBE_RESULTS_FILE = "function_live_probe_results.json"
FX_MAP_NODE_URI = f"{AUTHORING_PREFIX}/node/atomic/fxmaps"
SDF_VISUAL_ITERATION_UNITS = [
    {
        "unit": "sdf_function",
        "authoring_surface": "3D Viewer.sdf_scene or Shape Splatter v2.pattern_sdf_function",
        "preview_targets": ["3D Viewer.output", "Shape Splatter v2.sdf_color"],
        "pass_condition": "SDF silhouette and material channels are readable before downstream composition.",
    },
    {
        "unit": "shape_splatter",
        "authoring_surface": "Shape Splatter v2",
        "preview_targets": ["Shape Splatter v2.height", "Shape Splatter v2.sdf_color"],
        "pass_condition": "SDF contribution is visible in scattered height and color outputs.",
    },
    {
        "unit": "fx_map",
        "authoring_surface": "FX-Map graph",
        "preview_targets": ["FX-Map output"],
        "pass_condition": "Pattern has intentional density, scale, and composition before material blending.",
    },
    {
        "unit": "material_composite",
        "authoring_surface": "Package graph material outputs",
        "preview_targets": ["basecolor", "normal", "height", "roughness"],
        "pass_condition": "Final material visibly uses SDF and FX-Map contributions.",
    },
]
AUTHORING_REFERENCE_ALIASES = {
    f"{AUTHORING_PREFIX}/node/fx_map": FX_MAP_NODE_URI,
    f"{AUTHORING_PREFIX}/node/fx-map": FX_MAP_NODE_URI,
    f"{AUTHORING_PREFIX}/node/library/fx_map": FX_MAP_NODE_URI,
    f"{AUTHORING_PREFIX}/node/library/fx-map": FX_MAP_NODE_URI,
}
AUTHORING_CATEGORY_HINTS: dict[str, dict[str, Any]] = {
    "Splines & Paths/Spline": {
        "resource_kind": "node_category_hint",
        "summary": "Spline nodes generate, scatter, modify, sample, map, and render encoded spline streams.",
        "discovery_terms": [
            "spline",
            "path",
            "curve",
            "strand",
            "scatter",
            "warp",
            "deform",
            "bend",
            "curl",
            "render",
            "sample",
            "thickness",
            "height",
        ],
        "node_roles": {
            "spline_warp": {
                "use_when": "Existing splines need procedural displacement or noisy deformation before rendering, sampling, or mapping.",
                "not_for": "Changing only the placement side, amount, or rotation of scattered child splines; inspect scatter parameters for that.",
                "typical_chains": [
                    "Spline source -> Scatter Splines on Splines -> Spline Warp -> Spline Render",
                    "Spline source -> Spline Warp -> Spline Sample Height/Thickness -> Spline Render",
                ],
            },
            "scatter_splines_on_splines": {
                "use_when": "Child splines need to be placed along parent splines.",
                "not_for": "Deforming the already scattered spline geometry; use Spline Warp or sampling nodes downstream.",
                "typical_chains": [
                    "Parent Spline source -> Scatter Splines on Splines -> Spline Warp -> Spline Render",
                ],
            },
            "spline_render": {
                "use_when": "Encoded spline streams need to become grayscale or color texture output.",
                "not_for": "Editing spline geometry; place transform, warp, sample, select, or scatter nodes before rendering.",
                "typical_chains": [
                    "Spline source/editing nodes -> Spline Render -> downstream texture nodes",
                ],
            },
            "spline_sample_height": {
                "use_when": "Spline height should vary from a grayscale height map.",
                "not_for": "Changing 2D curve position; use Spline Warp or transform-like spline nodes.",
                "typical_chains": [
                    "Spline source -> Spline Sample Height -> Spline Render",
                ],
            },
            "spline_sample_thickness": {
                "use_when": "Spline thickness should vary from a grayscale thickness map.",
                "not_for": "Changing 2D curve position; use Spline Warp or transform-like spline nodes.",
                "typical_chains": [
                    "Spline source -> Spline Sample Thickness -> Spline Render",
                ],
            },
            "spline_cubic": {
                "use_when": "A single cubic spline source is needed between two points.",
                "not_for": "Downstream deformation of a spline list after scatter; search editing nodes before changing only cubic tangents.",
                "typical_chains": [
                    "Spline (Cubic) -> Scatter/append/edit spline nodes -> Spline Render",
                ],
            },
        },
    },
}


@lru_cache(maxsize=1)
def public_tool_names() -> tuple[str, ...]:
    """Return public tool names declared in the bundled skill catalog order."""
    resource = files("dcc_mcp_substancedesigner").joinpath("skills/substance-designer/tools.yaml")
    with as_file(resource) as tools_yaml:
        payload = load_yaml_file(tools_yaml)
    return tuple(
        str(tool["name"])
        for tool in payload.get("tools", [])
        if isinstance(tool, dict) and tool.get("group") == "public" and tool.get("name")
    )


def public_tool_action_id(public_name: str) -> str:
    """Return the concrete MCP action id for a bundled public tool."""
    if public_name not in public_tool_names():
        raise KeyError(public_name)
    return f"{ACTION_PREFIX}{public_name}"


@lru_cache(maxsize=1)
def public_tool_action_ids() -> dict[str, str]:
    """Return public tool action ids derived from tools.yaml."""
    return {name: public_tool_action_id(name) for name in public_tool_names()}
AUTHORING_CONTRACTS: dict[str, dict[str, Any]] = {
    "reference-first-policy": {
        "resource_kind": "authoring_contract",
        "slug": "reference-first-policy",
        "title": "Reference-first authoring policy",
        "description": "Required evidence policy for avoiding guessed Substance Designer graph edits.",
        "tools": [
            "get_graph",
            "get_node",
            "get_authoring_plan",
            "get_authoring_capabilities",
            "get_reference",
            "validate_graph_change",
        ],
        "priority_order": [
            "Inspect the live graph, node, controls, and property graph state with typed MCP tools.",
            "Request an authoring plan before requesting concrete authoring capabilities.",
            "Request context-specific authoring capabilities for the bounded unit before drafting a GraphChange.",
            "Read returned reference_uris with get_reference before mutating graph state.",
            "Use live get_node evidence for uncertain runtime ports, parameters, property graphs, or package resources.",
            "If local graph state and bundled resources are insufficient, direct the caller to official Substance Designer documentation or request live package/XML evidence.",
            "Stop instead of continuing with guessed identifiers, ports, parameters, Function Graph variables, or package resource names.",
        ],
        "unknowns_that_must_not_be_guessed": [
            "node definition ids",
            "library package file names or resource URLs",
            "input and output port ids",
            "parameter ids and writable value types",
            "Function Graph get_* __constant__ variables",
            "FX-Map or Pixel Processor property context variables",
            "output usage metadata",
        ],
        "acceptable_evidence": [
            "typed MCP scene or reference tool output",
            "substancedesigner://authoring resource contents read through get_reference",
            "reference_uris returned by inspection, validation, or summary tools",
            "existing property graph state returned by get_graph with a node-property GraphRef",
            "saved package/XML evidence supplied by the user",
            "official Adobe Substance Designer documentation",
        ],
        "fallback": {
            "when_evidence_is_missing": "Do not mutate the graph. Explain the missing fact and ask for a live inspection result, saved package evidence, or official documentation confirmation.",
            "web_docs": "Use official Substance Designer documentation when bundled resources do not cover an API, node, package, or Function Graph context.",
        },
        "discovery_resources": [
            f"{AUTHORING_PREFIX}/categories",
            f"{AUTHORING_PREFIX}/category/{{slug}}",
        ],
    },
    "graph-change": {
        "resource_kind": "authoring_contract",
        "slug": "graph-change",
        "title": "GraphChange contract",
        "description": "Contract for validate_graph_change and apply_graph_change.",
        "tools": ["get_authoring_capabilities", "validate_graph_change", "apply_graph_change", "replace_graph_state"],
        "payload": {
            "graph_ref": "GraphRef identifying a package graph, node property graph, or FX-Map graph.",
            "context": "Optional graph_kind plus FunctionContract metadata; inferred from GraphRef and prepared node definitions when possible.",
            "change.nodes": "Desired nodes with id, definition, optional position, optional parameters, and optional value. If id resolves to an existing host node, apply_graph_change updates that node; otherwise the id is a logical alias for a new node.",
            "change.nodes.definition": "Use the listed definition_id. Library definitions are declarative ids; apply_graph_change creates them as instance nodes using the node resource creation.resource_url.",
            "change.parameters": "Optional parameter list entries {'node': '<id_or_alias>', 'parameter': '<id>', 'value': ...}; these are normalized into the matching node parameter map and may be used alone for existing-node parameter updates.",
            "function_graph_instance_parameters": "For Function Graph library instance nodes, parameters that name connectable float/int inputs are lowered to constant nodes plus connections instead of direct host input-value mutation.",
            "change.connections": "Connections as endpoint objects: {'from': {'node': '<node_id_or_logical_id>', 'output': '<output_port>'}, 'to': {'node': '<node_id_or_logical_id>', 'input': '<input_port>'}}. Endpoints may reference nodes declared in this change or existing host node ids. Function graph builtins use {'from': {'builtin': '$pos'}, 'to': {'node': '<logical_id>', 'input': '<input_port>'}}.",
            "change.output": "FunctionContract output selected by logical node id or output object.",
            "change.omitted_state": "Unmentioned nodes, connections, outputs, and nested graphs are preserved. Full graph replacement is not part of apply_graph_change.",
            "package_graph_existing_state": "Package graph GraphChange patches existing nodes, moves nodes, removes input connections, and rewires existing inputs by snapshotting affected state before mutation and restoring it if a later operation fails.",
        },
        "response_contract": {
            "operation_plan": "validate_graph_change reports the apply-ready OperationPlan selected by the adapter.",
            "operation_plan.preserves_unmentioned": "True for valid apply_graph_change plans. If false, validation must fail.",
            "replace_graph_state": "Dedicated full-replacement workflow. It requires a complete state and the current state_hash from get_graph.",
            "capabilities": "Successful validation returns a compact response with capabilities omitted; invalid validation keeps capabilities for repair context.",
            "apply_strategy": "apply_graph_change echoes the strategy actually used.",
            "parameter_results": "Mutation responses separate parameter applied, skipped, and error entries. Empty lists mean no parameters were requested or affected.",
        },
        "reference_policy": {
            "required_policy": f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
            "node_definitions": [
                f"{AUTHORING_PREFIX}/nodes/function-atomic",
                f"{AUTHORING_PREFIX}/nodes/function-library",
                f"{AUTHORING_PREFIX}/node/function-atomic/{{slug}}",
                f"{AUTHORING_PREFIX}/node/function-library/{{slug}}",
                f"{AUTHORING_PREFIX}/node-definition/{{definition_id}}",
            ],
            "port_ids": "Only ids listed in node resource ports.inputs and ports.outputs are valid. Do not encode endpoints as 'node.port' strings.",
            "existing_nodes": "For package graphs, connections may target existing host node ids directly. Numeric nodes[].id values are treated as existing host nodes and updated instead of recreated.",
            "builtins": "Only FunctionContract builtins are valid. Shape Splatter readable variables such as shape.id are lowered to getter nodes; SDF P inputs may be left unconnected for the host-provided world position.",
            "editable_property_graphs": "get_node returns editable_property_graphs for function-backed node properties even when the child graph does not exist yet.",
            "library_nodes": "Nodes from substancedesigner://authoring/nodes/library expose creation.method=create_instance_node and creation.resource_url. Do not call low-level create_node for those resources.",
            "context_scopes": "Function-library nodes may require context_scopes such as 3d_viewer.",
            "plan": "Call get_authoring_plan before concrete capabilities when selecting an authoring unit.",
            "capabilities": "Call get_authoring_capabilities for the selected concrete unit before drafting a GraphChange.",
        },
    },
    "owner-input-binding": {
        "resource_kind": "authoring_contract",
        "slug": "owner-input-binding",
        "title": "Owner input binding contract",
        "description": "Contract for binding owner-node inputs to parameter-backed Function Graphs.",
        "tools": ["get_graph", "get_authoring_capabilities", "apply_graph_change", "get_node"],
        "graph_scopes": ["SDSBSCompGraph", "SDSBSFunctionGraph"],
        "rules": [
            "Owner-node inputs are separate from nodes inside the nested Function Graph.",
            "Use apply_graph_change with a node-property GraphRef as the public entry point for authoring parameter-backed Function Graphs.",
            "The adapter may create or reuse owner inputs internally when GraphChange support for owner-input bindings is available.",
            "Do not route normal graph input creation, parameter exposure, or dynamicValue binding workflows to .sbs XML edits.",
            "Function Graph get_* node __constant__ values must use bare variable ids such as foo, not #foo.",
            "Caller-supplied ids like #foo are normalized to foo before owner input creation and Function Graph application.",
            "Tool responses include requested_id, actual_property_id, and function_reference when an owner input is created or reused.",
            "If a mutation fails after owner-input creation, the error details report phase, rolled_back, partial_changes, and created_owner_inputs.",
            "Do not add label fields when creating Function Graph nodes or owner inputs; nested node ids are MCP logical aliases, not Substance Designer node labels.",
        ],
        "id_mapping": {
            "requested_id": "The caller-supplied owner input id, for example foo or #foo.",
            "actual_property_id": "The id observed on the Substance Designer owner input property.",
            "function_reference": "The normalized bare variable id used by get_* Function Graph nodes, for example foo.",
        },
        "verification": {
            "expose_parameter_workflow": [
                "get_node",
                "get_authoring_capabilities",
                "apply_graph_change",
                "get_graph or get_preview when needed",
            ],
            "after_mutation": [
                "get_graph",
                "get_node",
                "get_preview when rendered output matters",
            ],
            "next_tools": "Mutation responses include concrete next_tools entries for these checks.",
        },
    },
    "instance-node": {
        "resource_kind": "authoring_contract",
        "slug": "instance-node",
        "title": "Package instance node contract",
        "description": "Contract for creating a node instance from a loaded package resource URL.",
        "definition_pattern": "pkg://{resource_url}",
        "graph_scopes": ["SDSBSCompGraph"],
        "ports": {"inputs": [{"id": "*", "type": ["any"]}], "outputs": [{"id": "*", "type": ["any"]}]},
        "parameters": [],
        "root": {"can_be_root": False},
    },
    "compositing-graph-state": {
        "resource_kind": "authoring_contract",
        "slug": "compositing-graph-state",
        "title": "Compositing graph authoring contract",
        "description": "Contract for SDSBSCompGraph GraphChange authoring, instance nodes, connections, and output nodes.",
        "tools": [
            "get_authoring_capabilities",
            "validate_graph_change",
            "apply_graph_change",
            "get_node",
        ],
        "graph_scopes": ["SDSBSCompGraph"],
        "reference_policy": {
            "required_policy": f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
            "node_definitions": [
                f"{AUTHORING_PREFIX}/nodes/atomic",
                f"{AUTHORING_PREFIX}/nodes/library",
                f"{AUTHORING_PREFIX}/node/{{kind}}/{{slug}}",
                f"{AUTHORING_PREFIX}/node-definition/{{definition_id}}",
            ],
            "runtime_inspection": "Use get_node when runtime ports or parameters are uncertain.",
            "port_ids": "Use ids listed in node resources or get_node output.",
            "library_nodes": "Library node definitions are applied as package instance nodes through their creation.resource_url.",
        },
        "outputs": {
            "node_definition": "sbs::compositing::output",
            "input_port": "inputNodeOutput",
            "usage_metadata": ["identifier", "label", "usage"],
            "host_lowering": {
                "usage": "GraphChange public parameter 'usage' is lowered to the Substance Designer host property 'usages'. Do not declare 'usages' directly.",
            },
            "common_usages": [
                "baseColor",
                "normal",
                "height",
                "roughness",
                "metallic",
                "ambientOcclusion",
                "opacity",
                "emissive",
            ],
            "tool": "Use GraphChange nodes with the output node definition when material output nodes are required.",
        },
    },
    "node-introspection": {
        "resource_kind": "authoring_contract",
        "slug": "node-introspection",
        "title": "Runtime node introspection contract",
        "description": "Contract for get_node runtime evidence and static catalog comparison.",
        "tools": ["get_node"],
        "target": {
            "node_id": "Inspects an existing node in the selected graph without creating a temporary node.",
            "rule": "Exactly one node_id is accepted by the public get_node tool.",
        },
        "response": {
            "runtime": "Observed input ports, output ports, parameters, annotations, and nested graph references.",
            "static_reference": "Matched substancedesigner://authoring/node/{kind}/{slug} resource when available.",
            "comparison": "Best-effort id-level differences between runtime observation and static catalog.",
            "reference_uris": "Resources callers should read with get_reference before editing with the inspected node information.",
            "property_context": "Explicit notice when property-specific Function Graph context data is unavailable.",
            "evidence": "Live host observation metadata. It is evidence, not an automatic catalog update.",
        },
    },
    "operation-safety": {
        "resource_kind": "authoring_contract",
        "slug": "operation-safety",
        "title": "Substance Designer operation safety rules",
        "description": "Adapter-owned operational constraints for reliable graph authoring.",
        "rules": [
            "Follow the reference-first policy before any mutation: inspect live state, read returned reference_uris with get_reference, then stop if required evidence is missing.",
            "Do not guess library node ports; get_node should be used when ports are uncertain.",
            "Read reference_uris returned by inspection or validation tools with get_reference before editing graph state.",
            "Do not treat local skill paths, script paths, generated JSON files, or implementation files as authoring contracts.",
            "Do not invent property-backed Function Graph reserved variable names; require Resource, existing graph, XML, or live API evidence.",
            "Do not pass label fields when creating nodes. Substance Designer graph nodes are created by definition/resource and position; use frames or comments for human grouping.",
            "Input properties with runtime values are parameters; input properties without runtime values are connection ports.",
            "Blend opacity is a connection port; opacitymult is the scalar opacity parameter.",
            "Warp uses inputgradient for the warp map; directionalwarp uses inputintensity.",
            "Atomic outputs often use unique_filter_output, but library node output ids vary by resource.",
            "Use GraphChange nodes with the output node definition for material outputs.",
        ],
    },
}
AUTHORING_WORKFLOWS: dict[str, dict[str, Any]] = {
    "sdf-function": {
        "resource_kind": "authoring_workflow",
        "workflow_kind": "sdf_function",
        "slug": "sdf-function",
        "title": "SDF Function workflow",
        "description": "Designer 16.0+ SDF Function scene authoring through 3D Viewer and Shape Splatter v2.",
        "mental_model": "Author an SDF as a Function Graph over 3D point space P. Move, rotate, and scale space P before evaluating shapes instead of treating SDF primitives like ordinary placed objects.",
        "entrypoints": [
            "Create or inspect sbs::library::3d_viewer, then edit 3D Viewer.sdf_scene as an SDSBSFunctionGraph.",
            "Use get_node graph_surfaces to get the node_property_graph GraphRef for sdf_scene.",
        ],
        "visual_iteration_rule": (
            "For visual authoring, do not batch SDF, Shape Splatter, FX-Map, and material composition before "
            "preview. Preview and judge each visual unit before continuing."
        ),
        "visual_iteration_units": SDF_VISUAL_ITERATION_UNITS,
        "debug_controls": [
            "Set scene_type to SDF.",
            "Set enable_bounding_frame, colorize_out_of_frame, and enable_sdf_isolines to true while debugging.",
            "Set bounding_frame_size to the smallest frame that contains the SDF scene.",
        ],
        "production_use": [
            "For scattering, set Shape Splatter v2.shape_type to SDF Function and edit Shape Splatter v2.pattern_sdf_function.",
            "Keep Shape Splatter v2.sdf_bounding_frame_size aligned with the 3D Viewer bounding_frame_size used to author the shape.",
            "Use Set color, Set roughness, Set metalness, Set material, and Set ID nodes when SDF output maps or masks need those channels.",
            "Leave primitive P inputs unconnected when the default host-provided world position is intended.",
        ],
        "avoid": [
            "Do not use sbs::library::3d_texture_sdf / 3d_texture_sdf as the Designer 16 SDF Function scene-building entry point; it belongs to the 3D texture / volume render workflow.",
            "Do not search for SDF primitives directly in the outer SDSBSCompGraph; SDF primitives live inside an SDSBSFunctionGraph property graph.",
            "Do not guess enum integer meanings for scene_type or shape_type; use returned enum_options/current_label metadata.",
        ],
        "examples": [
            {
                "name": "sphere_smooth_union_set_color_roughness",
                "description": "Minimal SDF Function Graph pattern using two spheres, smooth union, color, and roughness.",
                "target_graph_ref": {
                    "kind": "node_property_graph",
                    "owner_definition": "sbs::library::3d_viewer",
                    "property_id": "sdf_scene",
                    "graph_type": "SDSBSFunctionGraph",
                },
                "graph_change": {
                    "nodes": [
                        {
                            "id": "sphere_a",
                            "definition": "sbs::function-library::3d_sdf_sphere",
                            "position": [0, 0],
                        },
                        {
                            "id": "offset_p",
                            "definition": "sbs::function-library::3d_sdf_transform_offset_p",
                            "position": [0, 160],
                            "parameters": {"offset": [0.35, 0, 0]},
                        },
                        {
                            "id": "sphere_b",
                            "definition": "sbs::function-library::3d_sdf_sphere",
                            "position": [260, 160],
                        },
                        {
                            "id": "smooth_union",
                            "definition": "sbs::function-library::3d_sdf_op_union_smooth",
                            "position": [520, 80],
                            "parameters": {"smoothness": 0.18},
                        },
                        {
                            "id": "color",
                            "definition": "sbs::function-library::set_color",
                            "position": [780, 40],
                            "parameters": {"color": {"r": 0.1, "g": 0.65, "b": 1.0, "a": 1.0}},
                        },
                        {
                            "id": "roughness",
                            "definition": "sbs::function-library::set_roughness",
                            "position": [1040, 40],
                            "parameters": {"roughness": 0.38},
                        },
                    ],
                    "connections": [
                        {
                            "from": {"node": "offset_p", "output": "unique_filter_output"},
                            "to": {"node": "sphere_b", "input": "P"},
                        },
                        {
                            "from": {"node": "sphere_a", "output": "unique_filter_output"},
                            "to": {"node": "smooth_union", "input": "sdf_a"},
                        },
                        {
                            "from": {"node": "sphere_b", "output": "unique_filter_output"},
                            "to": {"node": "smooth_union", "input": "sdf_b"},
                        },
                        {
                            "from": {"node": "smooth_union", "output": "unique_filter_output"},
                            "to": {"node": "color", "input": "sdf"},
                        },
                        {
                            "from": {"node": "color", "output": "unique_filter_output"},
                            "to": {"node": "roughness", "input": "sdf"},
                        },
                    ],
                    "output": "roughness",
                },
            }
        ],
        "reference_uris": [
            f"{AUTHORING_PREFIX}/node/library/3d_viewer",
            f"{AUTHORING_PREFIX}/node/library/shape_splatter_v2",
            f"{AUTHORING_PREFIX}/node/library/3d_texture_sdf",
            FUNCTION_CONTRACTS_URI,
        ],
    }
}


@lru_cache(maxsize=len(NODE_DEFINITION_KINDS))
def load_node_definition_set(kind: str) -> dict[str, Any]:
    """Return one packaged static node definition set."""
    if kind not in NODE_DEFINITION_KINDS:
        raise KeyError(kind)
    path = files(__package__).joinpath("node_definitions", NODE_DEFINITION_FILES[kind])
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_function_contract_registry() -> dict[str, Any]:
    """Return the packaged v2 FunctionContract registry."""
    path = files(__package__).joinpath("node_definitions", FUNCTION_CONTRACTS_FILE)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_fx_map_graph_definition() -> dict[str, Any]:
    """Return the packaged v2 FX-Map graph definition registry."""
    path = files(__package__).joinpath("node_definitions", FX_MAP_GRAPH_FILE)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_function_live_probe_results() -> dict[str, Any]:
    """Return live probe evidence used to build Function Graph node definitions."""
    path = files(__package__).joinpath("node_definitions", FUNCTION_LIVE_PROBE_RESULTS_FILE)
    return json.loads(path.read_text(encoding="utf-8"))


def node_definitions() -> list[dict[str, Any]]:
    """Return all static node definitions."""
    nodes = []
    for kind in NODE_DEFINITION_KINDS:
        nodes.extend(_node_definition_items(load_node_definition_set(kind), kind))
    return list(nodes)


def node_definition_by_id(definition_id: str) -> dict[str, Any] | None:
    """Return a static node definition by Substance Designer definition id."""
    matches = node_definitions_by_id(definition_id)
    return matches[0] if matches else None


def node_definitions_by_id(definition_id: str) -> list[dict[str, Any]]:
    """Return all static node definitions matching a Substance Designer definition id."""
    matches = []
    for node in _searchable_node_definitions():
        if node.get("definition_id") == definition_id:
            matches.append(node)
    return matches


def node_definition_by_kind_slug(kind: str, slug: str) -> dict[str, Any] | None:
    """Return a static node definition by URI kind and slug."""
    resolved = _resolve_node_slug(kind, slug)
    if resolved is None:
        return None
    resolved_slug, alias_score = resolved
    if kind in NODE_DEFINITION_KINDS:
        definitions = _node_definition_map(load_node_definition_set(kind))
        node = definitions.get(resolved_slug)
        if not isinstance(node, dict):
            return None
        payload = _node_with_identity(resolved_slug, kind, node)
        if resolved_slug != slug:
            payload["resolved_from"] = slug
            payload["resolution"] = {"method": "slug_similarity", "score": alias_score}
        return payload
    if kind == "fx-map":
        fx_map = load_fx_map_graph_definition().get("fx_map_graph")
        nodes = fx_map.get("nodes") if isinstance(fx_map, dict) else {}
        node = nodes.get(resolved_slug) if isinstance(nodes, dict) else None
        if not isinstance(node, dict):
            return None
        payload = {"slug": resolved_slug, "kind": kind, **node}
        if resolved_slug != slug:
            payload["resolved_from"] = slug
            payload["resolution"] = {"method": "slug_similarity", "score": alias_score}
        return payload
    return None


def _resolve_node_slug(kind: str, slug: str) -> tuple[str, float] | None:
    slugs = _node_slugs_for_kind(kind)
    if slug in slugs:
        return slug, 1.0
    candidates = _similar_node_slug_candidates(kind, slug, limit=2)
    if not candidates:
        return None
    best = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    if best["score"] >= 0.92 or (best["score"] >= 0.88 and best["score"] - second_score >= 0.04):
        return str(best["slug"]), float(best["score"])
    return None


def _node_slugs_for_kind(kind: str) -> set[str]:
    if kind in NODE_DEFINITION_KINDS:
        return set(_node_definition_map(load_node_definition_set(kind)))
    if kind == "fx-map":
        fx_map = load_fx_map_graph_definition().get("fx_map_graph")
        nodes = fx_map.get("nodes") if isinstance(fx_map, dict) else {}
        return set(nodes) if isinstance(nodes, dict) else set()
    return set()


def _similar_node_slug_candidates(kind: str, slug: str, *, limit: int = 5) -> list[dict[str, Any]]:
    candidates = []
    wanted_terms = set(_slug_terms(slug))
    for candidate in _node_slugs_for_kind(kind):
        score = SequenceMatcher(a=slug.lower(), b=candidate.lower()).ratio()
        candidate_terms = set(_slug_terms(candidate))
        if wanted_terms and wanted_terms <= candidate_terms:
            score = max(score, 0.94)
        if candidate_terms and candidate_terms <= wanted_terms:
            score = max(score, 0.90)
        if score >= 0.72:
            candidates.append(
                {
                    "slug": candidate,
                    "score": round(score, 4),
                    "uri": f"{AUTHORING_PREFIX}/node/{kind}/{candidate}",
                }
            )
    candidates.sort(key=lambda item: (-float(item["score"]), str(item["slug"])))
    return candidates[:limit]


def _fx_map_reference_suggestions(uri: str, slug: str) -> list[dict[str, Any]]:
    text = f"{uri} {slug}".lower().replace("-", "_")
    if "fx_map" not in text and "fxmap" not in text:
        return []
    return [
        {
            "slug": "fxmaps",
            "score": 1.0,
            "uri": FX_MAP_NODE_URI,
            "reason": "FX-Map is the atomic compositing node sbs::compositing::fxmaps.",
        },
        {
            "slug": "fx-map-graph",
            "score": 0.98,
            "uri": FX_MAP_GRAPH_URI,
            "reason": "FX-Map internals use the SDSBSFxMapGraph registry.",
        },
    ]


def _slug_terms(slug: str) -> list[str]:
    return [_normalize_slug_term(term) for term in re.split(r"[^a-z0-9]+", slug.lower()) if term]


def _normalize_slug_term(term: str) -> str:
    if len(term) <= 2:
        return term
    irregular = {
        "subtraction": "subtract",
        "addition": "add",
        "multiplication": "multiply",
        "division": "divide",
    }
    if term in irregular:
        return irregular[term]
    for suffix in ("ing", "ed", "es", "s"):
        if len(term) > len(suffix) + 2 and term.endswith(suffix):
            return term[: -len(suffix)]
    return term


def fx_map_node_definitions() -> list[dict[str, Any]]:
    """Return packaged FX-Map graph node definitions with public URI identity."""
    fx_map = load_fx_map_graph_definition().get("fx_map_graph")
    nodes = fx_map.get("nodes") if isinstance(fx_map, dict) else {}
    if not isinstance(nodes, dict):
        return []
    return [{"slug": slug, "kind": "fx-map", **node} for slug, node in nodes.items() if isinstance(node, dict)]


def node_index(kind: str | None = None) -> dict[str, Any]:
    """Return the lightweight node index resource payload."""
    if kind == "fx-map":
        entries = [_node_index_entry(node) for node in fx_map_node_definitions()]
        return {
            "schema_version": AUTHORING_SCHEMA_VERSION,
            "resource_kind": "node_index",
            "source": "static",
            "kind": kind,
            "count": len(entries),
            "entries": entries,
        }
    entries = []
    for node in node_definitions():
        if kind and node.get("kind") != kind:
            continue
        entries.append(_node_index_entry(node))
    return {
        "schema_version": AUTHORING_SCHEMA_VERSION,
        "resource_kind": "node_index",
        "source": "static",
        "kind": kind,
        "count": len(entries),
        "entries": entries,
    }


def _node_index_entry(node: dict[str, Any]) -> dict[str, Any]:
    ports = node.get("ports", {})
    input_count = (
        len(ports.get("inputs", {})) if isinstance(ports.get("inputs"), dict) else len(ports.get("inputs", []))
    )
    output_count = (
        len(ports.get("outputs", {})) if isinstance(ports.get("outputs"), dict) else len(ports.get("outputs", []))
    )
    return {
        "slug": node.get("slug"),
        "kind": node.get("kind"),
        "definition_id": node.get("definition_id"),
        "title": node.get("title") or node.get("display_name"),
        "display_name": node.get("display_name") or node.get("title"),
        "category": node.get("category", ""),
        "uri": f"{AUTHORING_PREFIX}/node/{node.get('kind')}/{node.get('slug')}",
        "graph_scopes": node.get("graph_scopes", []),
        "graph_kind": node.get("graph_kind"),
        "graph_type": node.get("graph_type"),
        "families": node.get("families", []),
        "context_scopes": node.get("context_scopes", []),
        "availability": node.get("availability", {}),
        "input_count": input_count,
        "output_count": output_count,
    }


def category_index() -> dict[str, Any]:
    """Return a lightweight index of node categories."""
    categories: dict[str, dict[str, Any]] = {}
    for node in node_definitions():
        category = str(node.get("category") or "Uncategorized")
        entry = categories.setdefault(
            category,
            {
                "category": category,
                "slug": _category_slug(category),
                "uri": f"{AUTHORING_PREFIX}/category/{_category_slug(category)}",
                "count": 0,
                "kinds": set(),
                "graph_scopes": set(),
                "hint_available": category in AUTHORING_CATEGORY_HINTS,
            },
        )
        entry["count"] += 1
        entry["kinds"].add(str(node.get("kind") or ""))
        for scope in _string_list(node.get("graph_scopes")):
            entry["graph_scopes"].add(scope)

    entries = []
    for item in sorted(categories.values(), key=lambda value: str(value["category"]).lower()):
        entries.append(
            {
                **item,
                "kinds": sorted(value for value in item["kinds"] if value),
                "graph_scopes": sorted(item["graph_scopes"]),
            }
        )
    return {
        "schema_version": AUTHORING_SCHEMA_VERSION,
        "resource_kind": "node_category_index",
        "source": "static",
        "count": len(entries),
        "entries": entries,
    }


def category_resource(slug: str) -> dict[str, Any] | None:
    """Return one category resource by slug."""
    category = _category_by_slug(slug)
    if category is None:
        return None
    nodes = [node for node in node_definitions() if str(node.get("category") or "Uncategorized") == category]
    entries = [_search_result_entry(node, score=0, reasons=["category"], include_details=False) for node in nodes]
    hint = AUTHORING_CATEGORY_HINTS.get(category, {})
    return {
        "schema_version": AUTHORING_SCHEMA_VERSION,
        "resource_kind": "node_category",
        "source": "static",
        "category": category,
        "slug": _category_slug(category),
        "count": len(entries),
        "hint": hint,
        "entries": entries,
    }


def search_node_references(
    query: str,
    *,
    kind: str | None = None,
    category: str | None = None,
    graph_scope: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search static node references by intent, category, and graph scope."""
    terms = _query_terms(query)
    kind = _optional_filter(kind)
    category = _optional_filter(category)
    graph_scope = _optional_filter(graph_scope)
    limit = max(1, min(int(limit), 50))
    workflow_matches = _workflow_matches_for_terms(terms, kind=kind, category=category, graph_scope=graph_scope)
    matches = []
    for node in _searchable_node_definitions():
        if kind and str(node.get("kind") or "").lower() != kind:
            continue
        node_category = str(node.get("category") or "Uncategorized")
        if category and category not in node_category.lower() and category != _category_slug(node_category):
            continue
        scopes = _string_list(node.get("graph_scopes"))
        if graph_scope and graph_scope not in [scope.lower() for scope in scopes]:
            continue
        score, reasons = _search_score(node, terms)
        if score <= 0:
            continue
        matches.append((score, node, reasons))

    matches.sort(key=lambda item: (-item[0], str(item[1].get("display_name") or item[1].get("slug"))))
    entries = [
        _search_result_entry(node, score=score, reasons=reasons, include_details=True)
        for score, node, reasons in matches[:limit]
    ]
    discovery_terms = _discovery_terms_for_matches([node for _, node, _ in matches[:limit]])
    return {
        "schema_version": AUTHORING_SCHEMA_VERSION,
        "resource_kind": "node_reference_search",
        "source": "static",
        "query": query,
        "filters": {
            "kind": kind,
            "category": category,
            "graph_scope": graph_scope,
            "limit": limit,
        },
        "count": len(entries),
        "workflow_matches": workflow_matches,
        "matches": entries,
        "reference_uris": _dedupe(
            [
                f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
                f"{AUTHORING_PREFIX}/categories",
                *[workflow["uri"] for workflow in workflow_matches if workflow.get("uri")],
                *[entry["uri"] for entry in entries],
                *[entry["category_uri"] for entry in entries if entry.get("category_uri")],
            ]
        ),
        "discovery_guidance": {
            "read_before_mutation": "Read the best matching node resources and inspect live node ports before editing graph structure.",
            "if_no_match": "Use official Substance Designer documentation or live package/XML evidence instead of guessing missing nodes.",
            "related_terms": discovery_terms,
        },
    }


def _searchable_node_definitions() -> list[dict[str, Any]]:
    return [*node_definitions(), *fx_map_node_definitions()]


def get_authoring_reference(uri: str) -> dict[str, Any]:
    """Return a public callable payload for one authoring reference URI."""
    uri = str(uri or "").strip()
    if not uri:
        raise ValueError("uri is required")
    if not uri.startswith(f"{AUTHORING_PREFIX}/"):
        raise ValueError(f"Unsupported Substance Designer authoring reference URI: {uri}")

    producer = SubstanceAuthoringReferenceProducer()
    resource = producer(uri)
    payload = json.loads(resource["text"])
    related_uris = _related_reference_uris(payload, current_uri=uri)
    return {
        "operation": GET_REFERENCE_TOOL,
        "ok": payload.get("resource_kind") != "not_found",
        "uri": uri,
        "mime_type": resource["mimeType"],
        "kind": payload.get("resource_kind"),
        "title": payload.get("title") or payload.get("display_name") or payload.get("name"),
        "content": payload,
        "related_uris": related_uris,
        "reference_uris": related_uris,
        "next_tools": _dedupe_next_tools([*reference_next_tools(related_uris), *_payload_next_tools(payload)]),
    }


def get_authoring_references(uris: list[str]) -> dict[str, Any]:
    """Return public callable payloads for multiple authoring reference URIs."""
    if not uris:
        raise ValueError("uri or uris is required")
    references = [get_authoring_reference(uri) for uri in uris]
    related_uris = _dedupe([uri for reference in references for uri in reference.get("related_uris", [])])
    return {
        "operation": GET_REFERENCE_TOOL,
        "ok": all(bool(reference.get("ok")) for reference in references),
        "count": len(references),
        "references": references,
        "related_uris": related_uris,
        "reference_uris": related_uris,
        "next_tools": reference_next_tools(related_uris),
    }


def reference_next_tools(reference_uris: Any) -> list[dict[str, Any]]:
    """Return callable next-tool hints for authoring reference URIs."""
    if not isinstance(reference_uris, list):
        return []
    return [
        tool_hint(GET_REFERENCE_TOOL, {"uri": uri})
        for uri in _dedupe([str(uri) for uri in reference_uris if isinstance(uri, str)])
        if uri.startswith(f"{AUTHORING_PREFIX}/") and "{" not in uri and "}" not in uri
    ]


def tool_hint(public_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a next_tools item that names the callable public MCP action id."""
    return {"tool": public_tool_action_id(public_name), "public_name": public_name, "args": args or {}}


def _payload_next_tools(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("resource_kind") != "authoring_contract":
        return []
    return [tool_hint(tool) for tool in _string_list(payload.get("tools")) if tool != GET_REFERENCE_TOOL]


def _dedupe_next_tools(next_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for item in next_tools:
        key = (str(item.get("tool")), repr(item.get("args", {})))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _contract_payload(contract: dict[str, Any]) -> dict[str, Any]:
    payload = dict(contract)
    action_ids = public_tool_action_ids()
    tools = [tool for tool in _string_list(payload.get("tools")) if tool in action_ids]
    payload["callable_tools"] = {tool: action_ids[tool] for tool in tools}
    return payload


def _node_resource_name(node: dict[str, Any]) -> str:
    return str(node.get("display_name") or node.get("title") or node.get("slug"))


def _node_resource_description(node: dict[str, Any]) -> str:
    parts = [str(node.get("definition_id"))]
    category = str(node.get("category") or "")
    if category:
        parts.append(category)
    description = str(node.get("description") or "").replace("\n", " ").strip()
    if description:
        parts.append(description[:180])
    return " | ".join(parts)


def _search_result_entry(
    node: dict[str, Any], *, score: int, reasons: list[str], include_details: bool
) -> dict[str, Any]:
    category = str(node.get("category") or "Uncategorized")
    slug = str(node.get("slug") or "")
    hint = AUTHORING_CATEGORY_HINTS.get(category, {}).get("node_roles", {}).get(slug, {})
    ports = node.get("ports", {}) if include_details else {}
    entry: dict[str, Any] = {
        "score": score,
        "reasons": reasons,
        "slug": slug,
        "kind": node.get("kind"),
        "definition_id": node.get("definition_id"),
        "display_name": node.get("display_name") or node.get("title"),
        "category": category,
        "category_uri": f"{AUTHORING_PREFIX}/category/{_category_slug(category)}",
        "uri": f"{AUTHORING_PREFIX}/node/{node.get('kind')}/{slug}",
        "graph_scopes": node.get("graph_scopes", []),
        "summary": _plain_text(node.get("description"))[:280],
    }
    if include_details:
        entry["ports"] = {
            "inputs": _port_refs(ports.get("inputs")),
            "outputs": _port_refs(ports.get("outputs")),
        }
        entry["parameters"] = _port_refs(node.get("parameters"))[:16]
    if hint:
        entry["use_when"] = hint.get("use_when")
        entry["not_for"] = hint.get("not_for")
        entry["typical_chains"] = hint.get("typical_chains", [])
    for key in ("workflow_warning", "workflow_roles", "workflow_uris"):
        if node.get(key):
            entry[key] = node[key]
    return entry


def _workflow_matches_for_terms(
    terms: list[str], *, kind: str | None, category: str | None, graph_scope: str | None
) -> list[dict[str, Any]]:
    if kind or category or graph_scope:
        return []
    term_set = set(terms)
    if not ({"sdf", "signed", "distance", "field"} & term_set or "signed_distance_field" in term_set):
        return []
    workflow = AUTHORING_WORKFLOWS["sdf-function"]
    return [
        {
            "score": 100,
            "slug": "sdf-function",
            "workflow_kind": workflow["workflow_kind"],
            "title": workflow["title"],
            "uri": SDF_FUNCTION_WORKFLOW_URI,
            "reason": (
                "For Substance Designer 16.0+ SDF authoring, read this workflow before selecting nodes; "
                "the outer graph only contains the entry nodes."
            ),
        }
    ]


def _search_score(node: dict[str, Any], terms: list[str]) -> tuple[int, list[str]]:
    reasons = []
    score = 0
    slug = str(node.get("slug") or "").lower()
    title = str(node.get("display_name") or node.get("title") or "").lower()
    category = str(node.get("category") or "").lower()
    description = _plain_text(node.get("description")).lower()
    definition_id = str(node.get("definition_id") or "").lower()
    parameter_ids = " ".join(str(item.get("id") or "") for item in _dict_list(node.get("parameters"))).lower()
    port_ids = " ".join(
        str(item.get("id") or "")
        for item in [
            *_dict_list((node.get("ports") or {}).get("inputs") if isinstance(node.get("ports"), dict) else None),
            *_dict_list((node.get("ports") or {}).get("outputs") if isinstance(node.get("ports"), dict) else None),
        ]
    ).lower()
    hint_terms = " ".join(
        _string_list(AUTHORING_CATEGORY_HINTS.get(str(node.get("category") or ""), {}).get("discovery_terms"))
    ).lower()
    role_hint = (
        AUTHORING_CATEGORY_HINTS.get(str(node.get("category") or ""), {})
        .get("node_roles", {})
        .get(str(node.get("slug") or ""), {})
    )
    role_text = " ".join(str(value) for value in role_hint.values() if isinstance(value, str)).lower()
    workflow_warning = node.get("workflow_warning") if isinstance(node.get("workflow_warning"), dict) else {}
    workflow_text = " ".join(str(value) for value in workflow_warning.values() if isinstance(value, str)).lower()

    for term in terms:
        term_score = 0
        if term == slug or term == definition_id:
            term_score += 80
            reasons.append(f"exact:{term}")
        if term in slug:
            term_score += 40
            reasons.append(f"slug:{term}")
        if term in title:
            term_score += 30
            reasons.append(f"title:{term}")
        if term in category:
            term_score += 18
            reasons.append(f"category:{term}")
        if term in parameter_ids:
            term_score += 12
            reasons.append(f"parameter:{term}")
        if term in port_ids:
            term_score += 12
            reasons.append(f"port:{term}")
        if term in description:
            term_score += 8
            reasons.append(f"description:{term}")
        if term in role_text:
            term_score += 24
            reasons.append(f"workflow:{term}")
        if term in workflow_text:
            term_score += 90
            reasons.append(f"workflow_warning:{term}")
        if term in hint_terms:
            term_score += 3
        score += term_score
    return score, _dedupe(reasons)


def _query_terms(query: str) -> list[str]:
    terms = [term for term in re.split(r"[^a-zA-Z0-9_:.-]+", query.lower()) if term]
    normalized = []
    for term in terms:
        normalized.append(term)
        if "-" in term:
            normalized.extend(part for part in term.split("-") if part)
        if "_" in term:
            normalized.extend(part for part in term.split("_") if part)
    return _dedupe(normalized)


def _discovery_terms_for_matches(nodes: list[dict[str, Any]]) -> list[str]:
    terms = []
    for node in nodes:
        terms.extend(
            _string_list(AUTHORING_CATEGORY_HINTS.get(str(node.get("category") or ""), {}).get("discovery_terms"))
        )
    return _dedupe(terms)[:24]


def _category_slug(category: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
    return slug or "uncategorized"


def _category_by_slug(slug: str) -> str | None:
    normalized = _category_slug(slug)
    for node in node_definitions():
        category = str(node.get("category") or "Uncategorized")
        if _category_slug(category) == normalized:
            return category
    return None


def _optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _plain_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _port_refs(value: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "display_name": item.get("display_name"),
            "type": item.get("type", []),
            "aliases": item.get("aliases", []),
            "connectable": item.get("connectable"),
            "primary": item.get("primary"),
        }
        for item in _dict_list(value)
    ]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [{**item, "id": key} for key, item in value.items() if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _node_definition_map(definition_set: dict[str, Any]) -> dict[str, Any]:
    nodes = definition_set.get("node_definitions")
    if isinstance(nodes, dict):
        return nodes
    nodes = definition_set.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _node_definition_items(definition_set: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [
        _node_with_identity(slug, kind, node)
        for slug, node in _node_definition_map(definition_set).items()
        if isinstance(node, dict)
    ]


def _node_with_identity(slug: str, kind: str, node: dict[str, Any]) -> dict[str, Any]:
    payload = {"slug": slug, "kind": kind, **node}
    if kind == "library":
        payload.setdefault(
            "creation",
            {
                "method": "create_instance_node",
                "resource_url": f"pkg:///{slug}",
                "resource_url_evidence": "derived_from_library_slug",
            },
        )
        _attach_library_workflow_metadata(payload, slug)
    else:
        payload.setdefault("creation", {"method": "create_node"})
    return payload


def _attach_library_workflow_metadata(payload: dict[str, Any], slug: str) -> None:
    if slug == "3d_texture_sdf":
        payload["workflow_warning"] = {
            "not_for": "sdf_function",
            "use_for": "3d_texture_volume_sdf",
            "message": (
                "3d_texture_sdf is not the Designer 16 SDF Function workflow entry point; "
                "use 3D Viewer.sdf_scene or Shape Splatter v2.pattern_sdf_function for SDF Function authoring."
            ),
            "workflow_uri": SDF_FUNCTION_WORKFLOW_URI,
        }
        return
    if slug == "3d_viewer":
        payload["workflow_roles"] = ["sdf_function_debug_entrypoint"]
        payload["workflow_uris"] = [SDF_FUNCTION_WORKFLOW_URI]
        return
    if slug == "shape_splatter_v2":
        payload["workflow_roles"] = ["sdf_function_production_consumer"]
        payload["workflow_uris"] = [SDF_FUNCTION_WORKFLOW_URI]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _related_reference_uris(payload: Any, *, current_uri: str) -> list[str]:
    values: list[str] = []
    _collect_reference_uris(payload, values)
    return [
        uri
        for uri in _dedupe(values)
        if uri != current_uri and uri.startswith(f"{AUTHORING_PREFIX}/") and "{" not in uri and "}" not in uri
    ][:50]


def _collect_reference_uris(value: Any, output: list[str]) -> None:
    if isinstance(value, str):
        if value.startswith(f"{AUTHORING_PREFIX}/"):
            output.append(value)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"resources", "resource_templates", "entries", "matches"}:
                continue
            _collect_reference_uris(item, output)
        return
    if isinstance(value, list):
        for item in value:
            _collect_reference_uris(item, output)


class SubstanceAuthoringReferenceProducer:
    """MCP resource producer for static graph authoring reference data."""

    def list_resources(self) -> list[dict[str, str]]:
        """Return concrete resources shown by resources/list."""
        resources = [
            {
                "uri": f"{AUTHORING_PREFIX}/index",
                "name": "Substance Designer authoring reference",
                "description": "Entry point for static Substance Designer node definitions and MCP authoring contracts.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": f"{AUTHORING_PREFIX}/nodes",
                "name": "Substance Designer node index",
                "description": "Lightweight index of static graph authoring node definitions.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": f"{AUTHORING_PREFIX}/categories",
                "name": "Substance Designer node category index",
                "description": "Lightweight index of static node categories for discovery before graph authoring.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": f"{AUTHORING_PREFIX}/contracts",
                "name": "Substance Designer authoring contracts",
                "description": "MCP authoring contracts that are not Substance Designer node definitions.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": FUNCTION_CONTRACTS_URI,
                "name": "Substance Designer FunctionContract registry",
                "description": "Packaged v2 Function Graph host-property contracts and output rules.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": FX_MAP_GRAPH_URI,
                "name": "Substance Designer FX-Map graph registry",
                "description": "Packaged v2 FX-Map graph node definitions.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": FUNCTION_LIVE_PROBE_RESULTS_URI,
                "name": "Substance Designer Function Graph live probe evidence",
                "description": "Live Substance Designer evidence used to build packaged function node definitions.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uri": SDF_FUNCTION_WORKFLOW_URI,
                "name": "Substance Designer SDF Function workflow",
                "description": "Designer 16.0+ SDF Function workflow guidance for 3D Viewer and Shape Splatter v2.",
                "mimeType": AUTHORING_MIME,
            },
        ]
        kinds = sorted({str(node.get("kind")) for node in node_definitions()} | {"fx-map"})
        for kind in kinds:
            resources.append(
                {
                    "uri": f"{AUTHORING_PREFIX}/nodes/{kind}",
                    "name": f"Substance Designer {kind} node index",
                    "description": f"Static index of {kind} node definitions.",
                    "mimeType": AUTHORING_MIME,
                }
            )
        for category in category_index()["entries"]:
            resources.append(
                {
                    "uri": str(category["uri"]),
                    "name": f"Substance Designer {category['category']} nodes",
                    "description": f"Static node category with {category['count']} entries.",
                    "mimeType": AUTHORING_MIME,
                }
            )
        for node in node_definitions():
            resources.append(
                {
                    "uri": f"{AUTHORING_PREFIX}/node/{node['kind']}/{node['slug']}",
                    "name": _node_resource_name(node),
                    "description": _node_resource_description(node),
                    "mimeType": AUTHORING_MIME,
                }
            )
        for slug, contract in AUTHORING_CONTRACTS.items():
            resources.append(
                {
                    "uri": f"{AUTHORING_PREFIX}/contracts/{slug}",
                    "name": str(contract.get("title") or slug),
                    "description": str(contract.get("description") or "Static MCP authoring contract."),
                    "mimeType": AUTHORING_MIME,
                }
            )
        return resources

    def list_resource_templates(self) -> list[dict[str, str]]:
        """Return MCP resource templates for parameterized authoring reference URIs."""
        return [
            {
                "uriTemplate": f"{AUTHORING_PREFIX}/node/{{kind}}/{{slug}}",
                "name": "Substance Designer node definition",
                "description": "Static Substance Designer node definition from the packaged atomic or library catalog.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uriTemplate": f"{AUTHORING_PREFIX}/node-definition/{{definition_id}}",
                "name": "Substance Designer node definition by definition id",
                "description": "Static authoring contract lookup by Substance Designer definition id.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uriTemplate": f"{AUTHORING_PREFIX}/category/{{slug}}",
                "name": "Substance Designer node category",
                "description": "Static category-specific node index for discovery before graph authoring.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uriTemplate": f"{AUTHORING_PREFIX}/contracts/{{slug}}",
                "name": "Substance Designer MCP authoring contract",
                "description": "Static MCP authoring contract that is not a Substance Designer node definition.",
                "mimeType": AUTHORING_MIME,
            },
            {
                "uriTemplate": f"{AUTHORING_PREFIX}/workflows/{{slug}}",
                "name": "Substance Designer authoring workflow",
                "description": "Static context-specific workflow guidance for graph authoring.",
                "mimeType": AUTHORING_MIME,
            },
        ]

    def __call__(self, uri: str) -> dict[str, str]:
        """Return resource contents for one authoring reference URI."""
        payload = self._payload_for_uri(uri)
        return {"mimeType": AUTHORING_MIME, "text": json.dumps(payload, sort_keys=True)}

    def _payload_for_uri(self, uri: str) -> dict[str, Any]:
        canonical_uri = AUTHORING_REFERENCE_ALIASES.get(uri)
        if canonical_uri:
            payload = self._payload_for_uri(canonical_uri)
            return {**payload, "canonical_uri": canonical_uri, "resolved_from": uri}
        if uri == f"{AUTHORING_PREFIX}/index":
            return {
                "schema_version": AUTHORING_SCHEMA_VERSION,
                "resource_kind": "authoring_index",
                "source": "static",
                "resources": self.list_resources(),
                "resource_templates": self.list_resource_templates(),
            }
        if uri == f"{AUTHORING_PREFIX}/nodes":
            return node_index()
        if uri == f"{AUTHORING_PREFIX}/categories":
            return category_index()
        if uri.startswith(f"{AUTHORING_PREFIX}/category/"):
            slug = uri.rsplit("/", 1)[-1]
            category = category_resource(slug)
            if category is not None:
                return category
        if uri.startswith(f"{AUTHORING_PREFIX}/nodes/"):
            kind = uri.rsplit("/", 1)[-1]
            return node_index(kind)
        if uri == f"{AUTHORING_PREFIX}/contracts":
            return {
                "schema_version": AUTHORING_SCHEMA_VERSION,
                "resource_kind": "authoring_contract_index",
                "count": len(AUTHORING_CONTRACTS),
                "entries": [
                    {
                        "slug": slug,
                        "title": contract.get("title"),
                        "uri": f"{AUTHORING_PREFIX}/contracts/{slug}",
                    }
                    for slug, contract in sorted(AUTHORING_CONTRACTS.items())
                ],
            }
        if uri == FUNCTION_CONTRACTS_URI:
            return load_function_contract_registry()
        if uri == FX_MAP_GRAPH_URI:
            return load_fx_map_graph_definition()
        if uri == FUNCTION_LIVE_PROBE_RESULTS_URI:
            return load_function_live_probe_results()
        if uri.startswith(f"{AUTHORING_PREFIX}/workflows/"):
            slug = uri.rsplit("/", 1)[-1]
            workflow = AUTHORING_WORKFLOWS.get(slug)
            if workflow is not None:
                return {
                    "schema_version": AUTHORING_SCHEMA_VERSION,
                    **workflow,
                }
        if uri.startswith(f"{AUTHORING_PREFIX}/contracts/"):
            slug = uri.rsplit("/", 1)[-1]
            contract = AUTHORING_CONTRACTS.get(slug)
            if contract is not None:
                return {
                    "schema_version": AUTHORING_SCHEMA_VERSION,
                    **_contract_payload(contract),
                }
        if uri.startswith(f"{AUTHORING_PREFIX}/node/"):
            parts = uri[len(f"{AUTHORING_PREFIX}/node/") :].split("/", 1)
            if len(parts) == 2:
                node = node_definition_by_kind_slug(parts[0], parts[1])
                if node is not None:
                    return {
                        "schema_version": AUTHORING_SCHEMA_VERSION,
                        "resource_kind": "node_definition",
                        **node,
                    }
                suggestions = _similar_node_slug_candidates(parts[0], parts[1])
                suggestions = _fx_map_reference_suggestions(uri, parts[1]) or suggestions
                return {
                    "schema_version": AUTHORING_SCHEMA_VERSION,
                    "resource_kind": "not_found",
                    "uri": uri,
                    "error": "Unknown Substance Designer node definition URI.",
                    "suggestions": suggestions,
                }
        if uri.startswith(f"{AUTHORING_PREFIX}/node-definition/"):
            definition_id = uri[len(f"{AUTHORING_PREFIX}/node-definition/") :]
            matches = node_definitions_by_id(definition_id)
            return {
                "schema_version": AUTHORING_SCHEMA_VERSION,
                "resource_kind": "node_definition_lookup",
                "definition_id": definition_id,
                "count": len(matches),
                "matches": [
                    {
                        "kind": node.get("kind"),
                        "slug": node.get("slug"),
                        "definition_id": node.get("definition_id"),
                        "display_name": node.get("display_name") or node.get("title"),
                        "category": node.get("category", ""),
                        "uri": f"{AUTHORING_PREFIX}/node/{node.get('kind')}/{node.get('slug')}",
                    }
                    for node in matches
                ],
            }
        return {
            "schema_version": AUTHORING_SCHEMA_VERSION,
            "resource_kind": "not_found",
            "uri": uri,
            "error": "Unknown Substance Designer authoring reference URI.",
        }
