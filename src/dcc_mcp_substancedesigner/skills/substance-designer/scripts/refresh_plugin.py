"""Refresh the running Substance Designer host plugin implementation."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry


@skill_entry
def main(include_raw: bool = False) -> dict:
    return run_workflow(
        "Refreshed Substance Designer host plugin",
        commands().refresh_plugin,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
