from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.database import get_dashboard_detail, get_dashboard_summary, list_dashboards
from app.dashboard_authoring import authoring_tool_specs, handle_authoring_tool_call
from app.github_tools import GITHUB_NAMESPACE, github_tool_specs, handle_github_tool_call
from app.metrics_provider import get_metrics_provider_for_org


TOOL_NAMESPACE = "chartdex"
MAX_TOOL_TEXT_CHARS = 40_000


@dataclass(frozen=True)
class ChartDexToolContext:
    app_db_path: Path
    org_id: str
    user_id: str
    thread_id: str


def dynamic_tool_specs() -> list[dict[str, object]]:
    return [
        {
            "namespace": TOOL_NAMESPACE,
            "name": "list_metrics",
            "description": "List the metrics available in ChartDex with formulas and business context.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "describe_metric",
            "description": "Get the definition and usage notes for one ChartDex metric.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["metric_id"],
                "properties": {"metric_id": {"type": "string"}},
            },
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "list_dimensions",
            "description": "List queryable metric dimensions and known values.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "list_business_events",
            "description": "List business events that may explain metric movement.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "list_experiments",
            "description": "List active and historical experiments represented in the metrics data.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "list_dashboards",
            "description": "List dashboards the authenticated ChartDex user can read.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "get_dashboard",
            "description": "Read one accessible dashboard with its panels and chart data.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dashboard_id"],
                "properties": {"dashboard_id": {"type": "string"}},
            },
            "exposeToContext": True,
        },
        {
            "namespace": TOOL_NAMESPACE,
            "name": "query_metrics",
            "description": (
                "Run a bounded structured metrics query. Metrics, dimensions, filters, and operators are "
                "allowlisted by ChartDex; raw SQL is not supported."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["metrics"],
                "properties": {
                    "metrics": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                    "granularity": {"type": "string", "enum": ["none", "day"]},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["field", "value"],
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string", "enum": ["=", "in"]},
                                "value": {},
                            },
                        },
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            },
            "exposeToContext": True,
        },
    ] + authoring_tool_specs() + github_tool_specs()


async def handle_tool_call(
    context: ChartDexToolContext,
    namespace: str | None,
    tool: str,
    arguments: Any,
) -> str:
    if namespace == GITHUB_NAMESPACE:
        return await handle_github_tool_call(context, tool, arguments)
    if namespace != TOOL_NAMESPACE:
        raise ValueError(f"Unsupported tool namespace: {namespace}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")

    authoring_result = await handle_authoring_tool_call(context, tool, arguments)
    if authoring_result is not None:
        return authoring_result

    provider = get_metrics_provider_for_org(context.app_db_path, context.org_id)
    if tool == "list_metrics":
        return tool_json({"metrics": provider.list_metric_catalog()})
    if tool == "describe_metric":
        metric = provider.describe_metric(required_string(arguments, "metric_id"))
        if metric is None:
            raise ValueError("Metric not found")
        return tool_json({"metric": metric})
    if tool == "list_dimensions":
        return tool_json({"dimensions": provider.list_dimensions()})
    if tool == "list_business_events":
        return tool_json({"events": provider.list_business_events()})
    if tool == "list_experiments":
        return tool_json({"experiments": provider.list_experiments()})
    if tool == "list_dashboards":
        org_dashboards = list_dashboards(context.app_db_path, org_id=context.org_id, space="org")
        personal_dashboards = list_dashboards(
            context.app_db_path,
            org_id=context.org_id,
            space="personal",
            owner_user_id=context.user_id,
        )
        return tool_json({"dashboards": [*org_dashboards, *personal_dashboards]})
    if tool == "get_dashboard":
        dashboard = get_dashboard_detail(
            context.app_db_path,
            dashboard_id=required_string(arguments, "dashboard_id"),
            org_id=context.org_id,
            user_id=context.user_id,
        )
        if dashboard is None:
            raise ValueError("Dashboard not found")
        return tool_json({"dashboard": dashboard})
    if tool == "query_metrics":
        query = dict(arguments)
        query["limit"] = min(int(query.get("limit", 100)), 200)
        return tool_json({"rows": provider.query_metrics(query)})
    raise ValueError(f"Unsupported tool: {tool}")


def validate_context_snapshot(
    app_db_path: Path,
    *,
    org_id: str,
    user_id: str,
    context: dict[str, object] | None,
) -> dict[str, object] | None:
    if context is None:
        return None
    allowed_keys = {"dashboard_id", "panel_id", "metric_key", "range_start", "range_end"}
    unknown_keys = set(context) - allowed_keys
    if unknown_keys:
        raise ValueError(f"Unsupported context fields: {', '.join(sorted(unknown_keys))}")

    dashboard_id = context.get("dashboard_id")
    if dashboard_id is None:
        return dict(context)
    if not isinstance(dashboard_id, str) or not dashboard_id:
        raise ValueError("context.dashboard_id must be a non-empty string")
    if get_dashboard_summary(app_db_path, dashboard_id=dashboard_id, org_id=org_id, user_id=user_id) is None:
        raise ValueError("Dashboard context is not accessible")

    dashboard = get_dashboard_detail(app_db_path, dashboard_id=dashboard_id, org_id=org_id, user_id=user_id)
    if dashboard is None:
        raise ValueError("Dashboard context is not accessible")
    panels = dashboard.get("panels", [])
    if not isinstance(panels, list):
        raise ValueError("Dashboard panels are invalid")

    panel_id = context.get("panel_id")
    panel = None
    if panel_id is not None:
        if not isinstance(panel_id, str) or not panel_id:
            raise ValueError("context.panel_id must be a non-empty string")
        panel = next((item for item in panels if isinstance(item, dict) and item.get("id") == panel_id), None)
        if panel is None:
            raise ValueError("Panel context does not belong to the dashboard")

    metric_key = context.get("metric_key")
    if metric_key is not None:
        if not isinstance(metric_key, str) or not metric_key:
            raise ValueError("context.metric_key must be a non-empty string")
        if panel is not None and panel.get("metric_key") != metric_key:
            raise ValueError("Metric context does not belong to the panel")

    return dict(context)


def tool_json(payload: dict[str, object]) -> str:
    text = json.dumps(payload, sort_keys=True, default=str)
    if len(text) > MAX_TOOL_TEXT_CHARS:
        return text[:MAX_TOOL_TEXT_CHARS] + "\n... truncated by ChartDex tool output limit"
    return text


def required_string(arguments: dict[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value
