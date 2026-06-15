"""Validate and apply a declarative graph change."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import OptionalSkillObjectInput


@skill_entry
def main(
    change: OptionalSkillObjectInput = None,
    graph_ref: OptionalSkillObjectInput = None,
    context: OptionalSkillObjectInput = None,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Applied Substance Designer graph change",
        commands().apply_graph_change,
        change=change,
        graph_ref=graph_ref,
        context=context,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
