"""Inspect a Substance Designer graph."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import (
    OptionalGraphIdentifierInput,
    OptionalNodeIdInput,
    OptionalReferenceInput,
    OptionalSkillObjectInput,
)


@skill_entry
def main(
    graph_ref: OptionalSkillObjectInput = None,
    graph_identifier: OptionalGraphIdentifierInput = None,
    owner_node_id: OptionalNodeIdInput = None,
    property_id: OptionalReferenceInput = None,
    graph_type: str | None = None,
    node_limit: int = 500,
    node_ids: list[str | int] | None = None,
    position_bounds: OptionalSkillObjectInput = None,
    detail_level: str = "structure",
    include_node_details: bool = False,
    include_parameters: bool = False,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Retrieved Substance Designer graph",
        commands().get_graph_state,
        graph_ref=graph_ref,
        graph_identifier=graph_identifier,
        owner_node_id=owner_node_id,
        property_id=property_id,
        graph_type=graph_type,
        node_limit=node_limit,
        node_ids=node_ids,
        position_bounds=position_bounds,
        detail_level=detail_level,
        include_node_details=include_node_details,
        include_parameters=include_parameters,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
