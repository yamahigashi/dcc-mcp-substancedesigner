"""Inspect a Substance Designer node."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import NodeIdInput, OptionalGraphIdentifierInput, OptionalSkillObjectInput


@skill_entry
def main(
    node_id: NodeIdInput = "",
    graph_ref: OptionalSkillObjectInput = None,
    graph_identifier: OptionalGraphIdentifierInput = None,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Retrieved Substance Designer node",
        commands().get_node_detail,
        node_id=node_id,
        graph_ref=graph_ref,
        graph_identifier=graph_identifier,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
