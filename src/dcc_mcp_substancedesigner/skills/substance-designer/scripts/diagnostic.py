"""Run Substance Designer adapter diagnostics."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry


@skill_entry
def main(include_raw: bool = False) -> dict:
    return run_workflow(
        "Retrieved Substance Designer diagnostics",
        commands().diagnostic,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
