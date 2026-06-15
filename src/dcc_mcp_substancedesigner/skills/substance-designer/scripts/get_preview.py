"""Render or retrieve a Substance Designer preview."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import (
    OptionalGraphIdentifierInput,
    OptionalNodeIdInput,
    OptionalResolutionDimensionInput,
)


@skill_entry
def main(
    node_id: OptionalNodeIdInput = None,
    graph_identifier: OptionalGraphIdentifierInput = None,
    node_output_id: str | None = None,
    channel: str = "rgba",
    resolution: str = "small",
    timeout_ms: int = 10000,
    width: OptionalResolutionDimensionInput = None,
    height: OptionalResolutionDimensionInput = None,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Retrieved Substance Designer preview",
        commands().get_preview,
        node_id=node_id,
        graph_identifier=graph_identifier,
        node_output_id=node_output_id,
        channel=channel,
        resolution=resolution,
        timeout_ms=timeout_ms,
        width=width,
        height=height,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
