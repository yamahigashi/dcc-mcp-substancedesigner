"""Tests for Substance Designer static authoring reference resources."""

from __future__ import annotations

import json

from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    FUNCTION_CONTRACTS_URI,
    FUNCTION_LIVE_PROBE_RESULTS_URI,
    FX_MAP_GRAPH_URI,
    SDF_FUNCTION_WORKFLOW_URI,
    SubstanceAuthoringReferenceProducer,
    category_resource,
    get_authoring_reference,
    get_authoring_references,
    load_node_definition_set,
    node_definition_by_id,
    reference_next_tools,
    search_node_references,
)
from dcc_mcp_substancedesigner.nested_graph_state import validate_nested_graph_state
from dcc_mcp_substancedesigner.reference_links import reference_uris_for_node_detail


def read_resource(uri: str) -> dict:
    result = SubstanceAuthoringReferenceProducer()(uri)
    assert result["mimeType"] == "application/json"
    return json.loads(result["text"])


def test_packaged_node_definition_sets_are_source_of_truth() -> None:
    atomic = load_node_definition_set("atomic")
    library = load_node_definition_set("library")
    function_atomic = load_node_definition_set("function-atomic")
    function_library = load_node_definition_set("function-library")

    assert atomic["resource_kind"] == "node_definition_set"
    assert atomic["count"] == 113
    assert library["resource_kind"] == "node_definition_set"
    assert library["count"] == 519
    assert function_atomic["resource_kind"] == "node_definition_set"
    assert function_atomic["schema_version"] == "2.0"
    assert "nodes" not in function_atomic
    assert len(function_atomic["node_definitions"]) == 84
    assert function_library["resource_kind"] == "node_definition_set"
    assert function_library["schema_version"] == "2.0"
    assert "nodes" not in function_library
    assert len(function_library["node_definitions"]) == 81
    assert atomic["nodes"]["swizzle1"]["ports"]["inputs"][0]["id"] == "vector"
    assert atomic["nodes"]["mul"]["ports"]["inputs"][0]["id"] == "a"
    assert atomic["nodes"]["mul"]["ports"]["inputs"][1]["id"] == "b"
    assert library["nodes"]["3d_perlin_noise"]["definition_id"] == "sbs::library::3D_perlin_noise"
    assert function_atomic["node_definitions"]["abs"]["definition_id"] == "sbs::function::abs"
    assert function_atomic["node_definitions"]["const_string"]["root"]["selectable"] is True
    assert function_atomic["node_definitions"]["const_string"]["root"]["blocked_contracts"] == {
        "pixel_processor": "output_type_mismatch",
        "value_processor": "value_processor_default_state_rejected",
    }
    assert (
        function_library["node_definitions"]["3d_sdf_capped_cone"]["definition_id"]
        == "sbs::function-library::3d_sdf_capped_cone"
    )
    assert function_library["node_definitions"]["3d_sdf_capped_cone"]["availability"]["requires_context"] == [
        "3d_viewer"
    ]


def test_authoring_resources_advertise_generated_catalogs_and_contracts() -> None:
    producer = SubstanceAuthoringReferenceProducer()

    resources = producer.list_resources()
    templates = producer.list_resource_templates()
    uris = {resource["uri"] for resource in resources}
    template_uris = {template["uriTemplate"] for template in templates}

    assert f"{AUTHORING_PREFIX}/nodes/atomic" in uris
    assert f"{AUTHORING_PREFIX}/nodes/library" in uris
    assert f"{AUTHORING_PREFIX}/nodes/function-atomic" in uris
    assert f"{AUTHORING_PREFIX}/nodes/function-library" in uris
    assert f"{AUTHORING_PREFIX}/nodes/fx-map" in uris
    assert f"{AUTHORING_PREFIX}/node/atomic/swizzle1" in uris
    assert f"{AUTHORING_PREFIX}/node/library/3d_perlin_noise" in uris
    assert f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_capped_cone" in uris
    assert f"{AUTHORING_PREFIX}/contracts/graph-change" in uris
    assert f"{AUTHORING_PREFIX}/contracts/reference-first-policy" in uris
    assert f"{AUTHORING_PREFIX}/contracts/instance-node" in uris
    assert f"{AUTHORING_PREFIX}/contracts/compositing-graph-state" in uris
    assert f"{AUTHORING_PREFIX}/contracts/node-introspection" in uris
    assert f"{AUTHORING_PREFIX}/contracts/operation-safety" in uris
    assert f"{AUTHORING_PREFIX}/workflows/sdf-function" in uris
    assert FUNCTION_CONTRACTS_URI in uris
    assert FX_MAP_GRAPH_URI in uris
    assert FUNCTION_LIVE_PROBE_RESULTS_URI in uris
    assert f"{AUTHORING_PREFIX}/node/{{kind}}/{{slug}}" in template_uris
    assert f"{AUTHORING_PREFIX}/node-definition/{{definition_id}}" in template_uris
    assert f"{AUTHORING_PREFIX}/category/{{slug}}" in template_uris
    assert f"{AUTHORING_PREFIX}/contracts/{{slug}}" in template_uris
    assert f"{AUTHORING_PREFIX}/workflows/{{slug}}" in template_uris
    assert sum(1 for uri in uris if uri.startswith(f"{AUTHORING_PREFIX}/node/")) == 797


def test_authoring_resources_expose_v2_contract_and_probe_registries() -> None:
    function_contracts = read_resource(FUNCTION_CONTRACTS_URI)
    fx_map_graph = read_resource(FX_MAP_GRAPH_URI)
    live_probe = read_resource(FUNCTION_LIVE_PROBE_RESULTS_URI)

    assert function_contracts["schema_version"] == "2.0"
    assert (
        function_contracts["function_contracts"]["sbs::compositing::pixelprocessor.perpixel"]["kind"]
        == "pixel_processor"
    )
    assert fx_map_graph["schema_version"] == "2.0"
    assert "sbs::fxmap::paramset" in {node["definition_id"] for node in fx_map_graph["fx_map_graph"]["nodes"].values()}
    assert live_probe["sd_version"] == "16.0.3"
    assert live_probe["generic_function_graph"]["nodes"]["sbs::function::const_string"]["selectable"] is True


def test_listed_node_resources_are_discoverable_by_definition_and_category() -> None:
    producer = SubstanceAuthoringReferenceProducer()
    resources = {resource["uri"]: resource for resource in producer.list_resources()}

    swizzle = resources[f"{AUTHORING_PREFIX}/node/atomic/swizzle1"]
    noise = resources[f"{AUTHORING_PREFIX}/node/library/3d_perlin_noise"]
    sdf = resources[f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_capped_cone"]

    assert "sbs::function::swizzle1" in swizzle["description"]
    assert "Swizzle Float1" == swizzle["name"]
    assert "sbs::library::3D_perlin_noise" in noise["description"]
    assert "Generator/Noise" in noise["description"]
    assert "sbs::function-library::3d_sdf_capped_cone" in sdf["description"]


def test_node_reference_resolves_close_slug_names_generically() -> None:
    subtract = read_resource(f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_op_subtract_smooth")
    scale = read_resource(f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_transform_scale_p")

    assert subtract["resource_kind"] == "node_definition"
    assert subtract["slug"] == "3d_sdf_op_subtraction_smooth"
    assert subtract["definition_id"] == "sbs::function-library::3d_sdf_op_subtraction_smooth"
    assert subtract["resolved_from"] == "3d_sdf_op_subtract_smooth"
    assert subtract["resolution"]["method"] == "slug_similarity"
    assert scale["resource_kind"] == "node_definition"
    assert scale["slug"] == "3d_sdf_transform_scale"
    assert scale["definition_id"] == "sbs::function-library::3d_sdf_transform_scale"


def test_node_reference_not_found_returns_close_slug_suggestions() -> None:
    result = read_resource(f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_subtract_smooth_missing")

    assert result["resource_kind"] == "not_found"
    assert result["suggestions"][0]["slug"] == "3d_sdf_op_subtraction_smooth"
    assert result["suggestions"][0]["uri"] == f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_op_subtraction_smooth"


def test_authoring_resource_indexes_expose_generated_catalog_counts() -> None:
    all_nodes = read_resource(f"{AUTHORING_PREFIX}/nodes")
    atomic_nodes = read_resource(f"{AUTHORING_PREFIX}/nodes/atomic")
    fx_map_nodes = read_resource(f"{AUTHORING_PREFIX}/nodes/fx-map")
    function_library_nodes = read_resource(f"{AUTHORING_PREFIX}/nodes/function-library")
    categories = read_resource(f"{AUTHORING_PREFIX}/categories")
    spline_category = read_resource(f"{AUTHORING_PREFIX}/category/splines-paths-spline")

    assert all_nodes["count"] == 797
    assert atomic_nodes["count"] == 113
    assert fx_map_nodes["count"] >= 3
    assert {entry["definition_id"] for entry in fx_map_nodes["entries"]} >= {
        "sbs::fxmap::paramset",
        "sbs::fxmap::markov2",
        "sbs::fxmap::addnode",
    }
    assert function_library_nodes["count"] == 81
    assert function_library_nodes["entries"][0]["context_scopes"]
    assert categories["resource_kind"] == "node_category_index"
    assert any(entry["slug"] == "splines-paths-spline" for entry in categories["entries"])
    assert spline_category["resource_kind"] == "node_category"
    assert spline_category["hint"]["node_roles"]["spline_warp"]["use_when"].startswith("Existing splines")
    assert any(entry["slug"] == "spline_warp" for entry in spline_category["entries"])


def test_search_node_reference_finds_spline_workflow_nodes() -> None:
    result = search_node_references(
        "spline bend warp curl deform",
        kind="library",
        category="spline",
        graph_scope="SDSBSCompGraph",
        limit=5,
    )

    assert result["resource_kind"] == "node_reference_search"
    assert result["matches"][0]["slug"] == "spline_warp"
    assert (
        "Spline source -> Scatter Splines on Splines -> Spline Warp -> Spline Render"
        in result["matches"][0]["typical_chains"]
    )
    assert f"{AUTHORING_PREFIX}/node/library/spline_warp" in result["reference_uris"]
    assert f"{AUTHORING_PREFIX}/category/splines-paths-spline" in result["reference_uris"]
    assert "warp" in result["discovery_guidance"]["related_terms"]
    assert category_resource("splines-paths-spline") is not None


def test_search_node_reference_surfaces_sdf_function_workflow_before_texture_sdf() -> None:
    result = search_node_references("sdf")

    assert result["workflow_matches"][0]["workflow_kind"] == "sdf_function"
    assert result["workflow_matches"][0]["uri"] == SDF_FUNCTION_WORKFLOW_URI
    assert SDF_FUNCTION_WORKFLOW_URI in result["reference_uris"]
    texture_match = next(match for match in result["matches"] if match["slug"] == "3d_texture_sdf")
    assert texture_match["workflow_warning"]["not_for"] == "sdf_function"


def test_search_node_reference_finds_fx_map_nodes() -> None:
    result = search_node_references("fxmap quadrant iterate switch", kind="fx-map")

    assert {match["definition_id"] for match in result["matches"]} >= {
        "sbs::fxmap::paramset",
        "sbs::fxmap::markov2",
        "sbs::fxmap::addnode",
    }
    assert f"{AUTHORING_PREFIX}/node/fx-map/paramset" in result["reference_uris"]


def test_sdf_workflow_example_does_not_use_unsupported_pos_builtin() -> None:
    workflow = read_resource(SDF_FUNCTION_WORKFLOW_URI)
    example = workflow["examples"][0]["graph_change"]

    assert all(connection.get("from", {}).get("builtin") != "$pos" for connection in example["connections"])
    assert "host-provided world position" in workflow["production_use"][-1]


def test_authoring_resource_reads_atomic_and_library_node_definitions() -> None:
    swizzle = read_resource(f"{AUTHORING_PREFIX}/node/atomic/swizzle1")
    noise = read_resource(f"{AUTHORING_PREFIX}/node/library/3d_perlin_noise")
    tile = read_resource(f"{AUTHORING_PREFIX}/node/library/tile_generator")
    sdf_texture = read_resource(f"{AUTHORING_PREFIX}/node/library/3d_texture_sdf")
    viewer = read_resource(f"{AUTHORING_PREFIX}/node/library/3d_viewer")
    splatter = read_resource(f"{AUTHORING_PREFIX}/node/library/shape_splatter_v2")
    sdf = read_resource(f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_capped_cone")
    fx_paramset = read_resource(f"{AUTHORING_PREFIX}/node/fx-map/paramset")

    assert swizzle["resource_kind"] == "node_definition"
    assert swizzle["definition_id"] == "sbs::function::swizzle1"
    assert swizzle["ports"]["inputs"][0]["id"] == "vector"
    assert swizzle["parameters"][0]["id"] == "__constant__"
    assert swizzle["parameters"][0]["required"] is False
    assert noise["resource_kind"] == "node_definition"
    assert noise["definition_id"] == "sbs::library::3D_perlin_noise"
    assert noise["ports"]["inputs"][0]["id"] == "position"
    assert tile["creation"]["method"] == "create_instance_node"
    assert tile["creation"]["resource_url"] == "pkg:///tile_generator"
    assert tile["creation"]["package"]["path"] == "pattern_tile_generator.sbs"
    assert tile["creation"]["package"]["evidence"] == {"source": "package_scan", "status": "complete"}
    assert sdf_texture["creation"]["method"] == "create_instance_node"
    assert sdf_texture["creation"]["resource_url"] == "pkg:///3d_texture_sdf"
    assert sdf_texture["creation"]["package"]["path"] == "3d_texture_jump_flood.sbs"
    assert sdf_texture["creation"]["standard_package_candidates"][0]["path"] == "3d_texture_jump_flood.sbs"
    assert sdf_texture["workflow_warning"]["not_for"] == "sdf_function"
    assert "Designer 16" in sdf_texture["workflow_warning"]["message"]
    assert "sdf_function_debug_entrypoint" in viewer["workflow_roles"]
    assert viewer["workflow_uris"] == [SDF_FUNCTION_WORKFLOW_URI]
    assert fx_paramset["resource_kind"] == "node_definition"
    assert fx_paramset["definition_id"] == "sbs::fxmap::paramset"
    assert fx_paramset["graph_type"] == "SDSBSFxMapGraph"
    assert "sdf_function_production_consumer" in splatter["workflow_roles"]
    assert splatter["workflow_uris"] == [SDF_FUNCTION_WORKFLOW_URI]
    shape_type = next(parameter for parameter in splatter["parameters"] if parameter["id"] == "shape_type")
    assert shape_type["enum"]["default_label"] == "Cube"
    assert shape_type["enum"]["options"][0] == {"id": "SDF Function", "label": "SDF Function", "value": 1}
    assert sdf["resource_kind"] == "node_definition"
    assert sdf["graph_type"] == "SDSBSFunctionGraph"
    assert sdf["families"] == ["sdf_function_library"]
    assert sdf["context_scopes"][0]["id"] == "3d_viewer"
    assert sdf["availability"]["default"] is False


def test_authoring_resource_definition_id_lookup_returns_duplicate_matches() -> None:
    lookup = read_resource(f"{AUTHORING_PREFIX}/node-definition/sbs::library::clamp")

    assert lookup["resource_kind"] == "node_definition_lookup"
    assert lookup["count"] == 2
    assert {match["slug"] for match in lookup["matches"]} == {"clamp", "clamp_2"}


def test_authoring_reference_callable_payload_exposes_next_tools() -> None:
    reference = get_authoring_reference(f"{AUTHORING_PREFIX}/contracts/graph-change")

    assert reference["operation"] == "get_reference"
    assert reference["ok"] is True
    assert reference["uri"] == f"{AUTHORING_PREFIX}/contracts/graph-change"
    assert reference["kind"] == "authoring_contract"
    assert reference["content"]["resource_kind"] == "authoring_contract"
    assert f"{AUTHORING_PREFIX}/contracts/reference-first-policy" in reference["related_uris"]
    assert {
        "tool": "substance_designer__get_reference",
        "public_name": "get_reference",
        "args": {"uri": f"{AUTHORING_PREFIX}/contracts/reference-first-policy"},
    } in reference["next_tools"]
    assert {
        "tool": "substance_designer__validate_graph_change",
        "public_name": "validate_graph_change",
        "args": {},
    } in reference["next_tools"]
    assert {
        "tool": "substance_designer__apply_graph_change",
        "public_name": "apply_graph_change",
        "args": {},
    } in reference["next_tools"]


def test_fx_map_reference_alias_and_unknown_uri_suggest_canonical_entries() -> None:
    alias = get_authoring_reference(f"{AUTHORING_PREFIX}/node/library/fx_map")

    assert alias["ok"] is True
    assert alias["content"]["resource_kind"] == "node_definition"
    assert alias["content"]["definition_id"] == "sbs::compositing::fxmaps"
    assert alias["content"]["canonical_uri"] == f"{AUTHORING_PREFIX}/node/atomic/fxmaps"

    missing = get_authoring_reference(f"{AUTHORING_PREFIX}/node/library/fx_map_missing")
    assert missing["ok"] is False
    suggestion_uris = {item["uri"] for item in missing["content"]["suggestions"]}
    assert f"{AUTHORING_PREFIX}/node/atomic/fxmaps" in suggestion_uris
    assert FX_MAP_GRAPH_URI in suggestion_uris


def test_compositing_graph_contract_exposes_single_public_output_usage_key() -> None:
    reference = get_authoring_reference(f"{AUTHORING_PREFIX}/contracts/compositing-graph-state")

    outputs = reference["content"]["outputs"]
    assert outputs["usage_metadata"] == ["identifier", "label", "usage"]
    assert "usages" not in outputs["usage_metadata"]
    assert "usages" in outputs["host_lowering"]["usage"]


def test_sdf_function_workflow_reference_separates_texture_sdf_from_function_workflow() -> None:
    reference = get_authoring_reference(f"{AUTHORING_PREFIX}/workflows/sdf-function")

    content = reference["content"]
    assert content["resource_kind"] == "authoring_workflow"
    assert content["workflow_kind"] == "sdf_function"
    assert "3D Viewer.sdf_scene" in content["entrypoints"][0]
    assert "recommended_sequence" not in content
    assert [unit["unit"] for unit in content["visual_iteration_units"]] == [
        "sdf_function",
        "shape_splatter",
        "fx_map",
        "material_composite",
    ]
    assert all(unit["preview_targets"] for unit in content["visual_iteration_units"])
    assert all(unit["pass_condition"] for unit in content["visual_iteration_units"])
    assert any("3d_texture_sdf" in item for item in content["avoid"])
    assert "Shape Splatter v2.pattern_sdf_function" in content["production_use"][0]
    assert content["examples"][0]["name"] == "sphere_smooth_union_set_color_roughness"
    example = content["examples"][0]["graph_change"]
    definitions = {node["definition"] for node in example["nodes"]}
    assert "sbs::function-library::3d_sdf_sphere" in definitions
    assert "sbs::function-library::3d_sdf_op_union_smooth" in definitions
    assert "sbs::function-library::set_color" in definitions
    assert "sbs::function-library::set_roughness" in definitions
    assert f"{AUTHORING_PREFIX}/node/library/3d_viewer" in reference["related_uris"]
    assert f"{AUTHORING_PREFIX}/node/library/3d_texture_sdf" in reference["related_uris"]


def test_authoring_reference_callable_accepts_multiple_uris() -> None:
    references = get_authoring_references(
        [
            f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
            f"{AUTHORING_PREFIX}/node/atomic/swizzle1",
        ]
    )

    assert references["operation"] == "get_reference"
    assert references["ok"] is True
    assert references["count"] == 2
    assert references["references"][0]["kind"] == "authoring_contract"
    assert references["references"][1]["kind"] == "node_definition"


def test_reference_next_tools_filters_templates_and_non_reference_values() -> None:
    assert reference_next_tools(
        [
            f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
            f"{AUTHORING_PREFIX}/node/{{kind}}/{{slug}}",
            "file:///tmp/internal.json",
        ]
    ) == [
        {
            "tool": "substance_designer__get_reference",
            "public_name": "get_reference",
            "args": {"uri": f"{AUTHORING_PREFIX}/contracts/reference-first-policy"},
        }
    ]


def test_authoring_contracts_are_not_node_definitions() -> None:
    index = read_resource(f"{AUTHORING_PREFIX}/contracts")
    graph_change = read_resource(f"{AUTHORING_PREFIX}/contracts/graph-change")
    contract = read_resource(f"{AUTHORING_PREFIX}/contracts/instance-node")
    compositing = read_resource(f"{AUTHORING_PREFIX}/contracts/compositing-graph-state")
    introspection = read_resource(f"{AUTHORING_PREFIX}/contracts/node-introspection")
    owner_input = read_resource(f"{AUTHORING_PREFIX}/contracts/owner-input-binding")
    reference_first = read_resource(f"{AUTHORING_PREFIX}/contracts/reference-first-policy")
    safety = read_resource(f"{AUTHORING_PREFIX}/contracts/operation-safety")

    assert index["resource_kind"] == "authoring_contract_index"
    assert index["count"] == 7
    assert graph_change["resource_kind"] == "authoring_contract"
    assert graph_change["callable_tools"]["apply_graph_change"] == "substance_designer__apply_graph_change"
    assert graph_change["reference_policy"]["required_policy"] == f"{AUTHORING_PREFIX}/contracts/reference-first-policy"
    assert graph_change["reference_policy"]["port_ids"].startswith("Only ids listed")
    assert f"{AUTHORING_PREFIX}/nodes/function-library" in graph_change["reference_policy"]["node_definitions"]
    assert contract["resource_kind"] == "authoring_contract"
    assert contract["definition_pattern"] == "pkg://{resource_url}"
    assert compositing["outputs"]["input_port"] == "inputNodeOutput"
    assert compositing["callable_tools"]["get_node"] == "substance_designer__get_node"
    assert introspection["target"]["rule"].startswith("Exactly one")
    assert "node_id" in introspection["target"]
    assert "definition_id" not in introspection["target"]
    assert "resource_url" not in introspection["target"]
    assert "property_id" not in introspection["target"]
    assert owner_input["id_mapping"]["function_reference"].endswith("for example foo.")
    assert owner_input["callable_tools"]["apply_graph_change"] == "substance_designer__apply_graph_change"
    assert owner_input["callable_tools"]["get_graph"] == "substance_designer__get_graph"
    assert any(".sbs XML" in rule for rule in owner_input["rules"])
    assert reference_first["resource_kind"] == "authoring_contract"
    assert reference_first["callable_tools"]["get_reference"] == "substance_designer__get_reference"
    assert reference_first["fallback"]["when_evidence_is_missing"].startswith("Do not mutate")
    assert "parameter ids and writable value types" in reference_first["unknowns_that_must_not_be_guessed"]
    assert any("implementation files" in rule for rule in safety["rules"])
    assert any("directionalwarp" in rule for rule in safety["rules"])
    assert any("reference-first policy" in rule for rule in safety["rules"])
    assert node_definition_by_id("pkg://{resource_url}") is None


def test_node_detail_references_do_not_emit_retired_nested_graph_contract() -> None:
    references = reference_uris_for_node_detail(
        {
            "definition": "sbs::compositing::pixelprocessor",
            "is_library_node": False,
            "nested_graph_refs": [{"property": "perpixel"}],
        }
    )

    assert f"{AUTHORING_PREFIX}/contracts/nested-graph-state" not in references
    assert f"{AUTHORING_PREFIX}/contracts/node-introspection" in references
    assert f"{AUTHORING_PREFIX}/contracts/compositing-graph-state" in references


def test_node_detail_references_use_resolved_instance_definition() -> None:
    references = reference_uris_for_node_detail(
        {
            "definition": "sbs::compositing::sbscompgraph_instance",
            "resolved_definition": "sbs::library::shape_splatter_v2",
            "is_library_node": True,
            "nested_graph_refs": [{"property": "pattern_sdf_function"}],
        }
    )

    assert f"{AUTHORING_PREFIX}/node/library/shape_splatter_v2" in references
    assert f"{AUTHORING_PREFIX}/node-definition/sbs::library::shape_splatter_v2" in references


def test_nested_graph_validation_uses_generated_atomic_ports() -> None:
    valid = {
        "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "uv", "definition": "sbs::function::get_float2"},
            {"id": "x", "definition": "sbs::function::swizzle1", "parameters": {"__constant__": {"value": 0}}},
        ],
        "connections": [
            {"from": "uv", "from_output": "unique_filter_output", "to": "x", "to_input": "vector"},
        ],
        "output": {"node": "x"},
    }

    valid_result = validate_nested_graph_state(valid)

    assert valid_result["valid"] is True


def test_nested_graph_validation_reports_reference_uris_for_catalog_errors() -> None:
    invalid = {
        "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "uv", "definition": "sbs::function::get_float2"},
            {"id": "x", "definition": "sbs::function::swizzle1", "parameters": {"__constant__": {"value": 0}}},
        ],
        "connections": [
            {"from": "uv", "from_output": "unique_filter_output", "to": "x", "to_input": "missing_port"},
        ],
        "output": {"node": "x"},
    }

    result = validate_nested_graph_state(invalid)

    assert result["valid"] is False
    assert f"{AUTHORING_PREFIX}/node/atomic/swizzle1" in result["reference_uris"]


def test_nested_graph_validation_warns_for_context_scoped_function_library_nodes() -> None:
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "shape_1", "property": "field"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "sdf", "definition": "sbs::function-library::3d_sdf_capped_cone"},
        ],
        "connections": [],
        "output": {"node": "sdf"},
    }

    result = validate_nested_graph_state(state)

    assert result["valid"] is True
    assert result["warnings"][0]["type"] == "context_scope_required"
    assert result["warnings"][0]["required_contexts"] == ["3d_viewer"]
    assert result["warnings"][0]["resource_uri"] == f"{AUTHORING_PREFIX}/node/function-library/3d_sdf_capped_cone"
