"""Execute trusted local Python in the connected Substance Designer process."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry


@skill_entry
def main(code: str = "", strict_json: bool = False, include_raw: bool = False) -> dict:
    return run_workflow(
        "Executed Substance Designer Python",
        commands().execute_python,
        code=code,
        strict_json=strict_json,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
