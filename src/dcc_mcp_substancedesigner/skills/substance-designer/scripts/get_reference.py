"""Read Substance Designer authoring reference resources through a callable tool."""

from __future__ import annotations

from _workflow_common import run_workflow
from dcc_mcp_core.skill import skill_entry

from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    get_authoring_reference,
    get_authoring_references,
)
from dcc_mcp_substancedesigner.commands import SubstanceDesignerValidationError


def _get_reference(*, uri: str = "", uris: list[str] | None = None) -> dict:
    if uris:
        _validate_uri_list(uris)
        return get_authoring_references(uris)
    _validate_uri(uri)
    return get_authoring_reference(uri)


def _validate_uri(uri: str) -> None:
    uri = str(uri or "").strip()
    if not uri:
        raise SubstanceDesignerValidationError("uri or uris is required")
    if not uri.startswith(f"{AUTHORING_PREFIX}/"):
        raise SubstanceDesignerValidationError(f"Unsupported Substance Designer authoring reference URI: {uri}")


def _validate_uri_list(uris: list[str]) -> None:
    if not isinstance(uris, list) or not uris:
        raise SubstanceDesignerValidationError("uri or uris is required")
    for uri in uris:
        _validate_uri(uri)


@skill_entry
def main(uri: str = "", uris: list[str] | None = None) -> dict:
    return run_workflow(
        "Retrieved Substance Designer authoring reference",
        _get_reference,
        uri=uri,
        uris=uris,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
