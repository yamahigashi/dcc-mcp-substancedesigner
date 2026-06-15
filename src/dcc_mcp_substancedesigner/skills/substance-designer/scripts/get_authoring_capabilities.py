"""Return context-specific graph authoring capabilities."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.input_types import OptionalSkillObjectInput


@skill_entry
def main(
    graph_ref: OptionalSkillObjectInput = None,
    context: OptionalSkillObjectInput = None,
    intent: str | None = None,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Retrieved Substance Designer graph authoring capabilities",
        commands().get_authoring_capabilities,
        graph_ref=graph_ref,
        context=context,
        intent=intent,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
