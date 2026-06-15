"""Shared helpers for public Substance Designer workflow tools."""

from __future__ import annotations

from typing import Any, Callable

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_substancedesigner.authoring_reference import reference_next_tools
from dcc_mcp_substancedesigner.bridge import SubstanceDesignerBridgeError
from dcc_mcp_substancedesigner.commands import SubstanceDesignerValidationError, commands_from_env


def commands():
    """Return the environment-configured command facade."""
    return commands_from_env()


def run_workflow(label: str, operation: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Run a Substance Designer workflow operation and wrap it as a skill result."""
    try:
        payload = operation(**kwargs)
        payload = attach_reference_next_tools(payload)
        if payload.get("operation") == "execute_python" and payload.get("ok") is False:
            return skill_error(
                "Substance Designer Python execution failed",
                str(payload.get("execution_message") or payload.get("stderr") or "Python execution failed"),
                **payload,
            )
        if payload.get("operation") == "apply_graph_change" and _graph_change_applied(payload) is False:
            rolled_back = _graph_change_rolled_back(payload)
            message = "Graph change failed and was rolled back" if rolled_back else "Graph change failed"
            detail = _graph_change_error(payload) or message
            return skill_error(message, detail, **payload)
        return skill_success(label, **payload)
    except SubstanceDesignerValidationError as exc:
        return skill_error("Invalid Substance Designer tool input", str(exc))
    except SubstanceDesignerBridgeError as exc:
        if _is_node_lookup_graph_error(exc):
            return skill_error(
                "Substance Designer node lookup failed",
                str(exc),
                bridge_error_details=exc.details,
                possible_solutions=[
                    "Retry with graph_identifier from bridge_error_details.resolved_graph_identifier or current_graph.",
                    "Call get_scene to inspect current_graph before calling get_node with only node_id.",
                    "If the node was just created by apply_graph_change, reuse that request's graph_ref.graph_identifier.",
                ],
            )
        return skill_error(
            "Substance Designer bridge request failed",
            str(exc),
            bridge_error_details=exc.details,
            possible_solutions=[
                "Start Substance Designer 16.0+.",
                "Load the dcc-mcp-substancedesigner plugin.",
                "Check DCC_MCP_SUBSTANCEDESIGNER_HOST and DCC_MCP_SUBSTANCEDESIGNER_PORT.",
            ],
        )
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to {label.lower()}")


def attach_reference_next_tools(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach callable reference-reader hints whenever a payload has reference URIs."""
    if not isinstance(payload, dict):
        return payload
    reference_uris = _collect_reference_uris(payload)
    existing = _collect_next_tools(payload)
    next_tools = [*existing, *reference_next_tools(reference_uris)]
    if not next_tools:
        return payload
    return {**payload, "reference_uris": reference_uris, "next_tools": _dedupe_next_tools(next_tools)}


def _graph_change_applied(payload: dict[str, Any]) -> bool | None:
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("applied"), bool):
        return result["applied"]
    value = payload.get("applied")
    return value if isinstance(value, bool) else None


def _is_node_lookup_graph_error(exc: SubstanceDesignerBridgeError) -> bool:
    details = exc.details
    if not isinstance(details, dict):
        return False
    if "node_id" not in details:
        return False
    return "resolved_graph_identifier" in details or "current_graph" in details


def _graph_change_rolled_back(payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("rolled_back"), bool):
        return result["rolled_back"]
    return bool(payload.get("rolled_back"))


def _graph_change_error(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])
    if payload.get("error"):
        return str(payload["error"])
    return ""


def _collect_reference_uris(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe_strings([uri for item in value for uri in _collect_reference_uris(item)])
    if not isinstance(value, dict):
        return []
    uris: list[str] = []
    direct = value.get("reference_uris")
    if isinstance(direct, list):
        uris.extend(str(uri) for uri in direct if isinstance(uri, str))
    for key in ("result", "validation"):
        uris.extend(_collect_reference_uris(value.get(key)))
    return _dedupe_strings(uris)


def _collect_next_tools(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [tool for item in value for tool in _collect_next_tools(item)]
    if not isinstance(value, dict):
        return []
    tools = [item for item in value.get("next_tools", []) if isinstance(item, dict)]
    for key in ("result", "validation"):
        tools.extend(_collect_next_tools(value.get(key)))
    return tools


def _dedupe_next_tools(next_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for item in next_tools:
        key = (item.get("tool"), repr(item.get("args", {})))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
