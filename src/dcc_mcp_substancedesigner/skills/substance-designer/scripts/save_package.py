"""Save a Substance Designer package."""

from __future__ import annotations

from _workflow_common import commands, run_workflow
from dcc_mcp_core.skill import skill_entry


@skill_entry
def main(
    package_index: int = 0,
    file_path: str | None = None,
    package_path: str | None = None,
    include_raw: bool = False,
) -> dict:
    return run_workflow(
        "Saved Substance Designer package",
        commands().save_package,
        package_index=package_index,
        file_path=file_path,
        package_path=package_path,
        include_raw=include_raw,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
