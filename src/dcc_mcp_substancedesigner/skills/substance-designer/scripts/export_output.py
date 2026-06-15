"""Export a Substance Designer node output to a file."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import OptionalGraphIdentifierInput, OptionalNodeIdInput


@skill_entry
def main(
    node_id: OptionalNodeIdInput = None,
    file_path: str | None = None,
    graph_identifier: OptionalGraphIdentifierInput = None,
    node_output_id: str | None = None,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Exported Substance Designer node output",
        commands().export_output,
        node_id=node_id,
        file_path=file_path,
        graph_identifier=graph_identifier,
        node_output_id=node_output_id,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
