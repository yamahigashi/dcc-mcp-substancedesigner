"""Replace a complete nested graph state after validating the current state hash."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import OptionalSkillObjectInput


@skill_entry
def main(
    graph_ref: OptionalSkillObjectInput = None,
    state: OptionalSkillObjectInput = None,
    expected_current_hash: str = "",
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Replaced Substance Designer graph state",
        commands().replace_graph_state,
        graph_ref=graph_ref,
        state=state,
        expected_current_hash=expected_current_hash,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
