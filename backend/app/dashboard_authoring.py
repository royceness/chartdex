from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.database import create_draft_dashboard, create_draft_panel, get_dashboard_detail, list_dashboards
from app.metrics_provider import get_metrics_provider_for_org

if TYPE_CHECKING:
    from app.codex_tools import ChartDexToolContext


ALLOWED_PANEL_TYPES = {"line", "bar"}
ALLOWED_VALUE_FORMATS = {"currency", "percent", "integer"}
ALLOWED_FILTER_OPERATORS = {"=", "in"}
MAX_AUTHORING_LIMIT = 200


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def authoring_tool_specs() -> list[dict[str, object]]:
    panel_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "type", "value_format", "description", "query"],
        "properties": {
            "title": {"type": "string"},
            "type": {"type": "string", "enum": ["line", "bar"]},
            "value_format": {"type": "string", "enum": ["currency", "percent", "integer"]},
            "description": {"type": "string"},
            "query": {
                "type": "object",
                "additionalProperties": False,
                "required": ["metrics", "dimensions"],
                "properties": {
                    "metrics": {"type": "array", "minItems": 1, "maxItems": 1, "items": {"type": "string"}},
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
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_AUTHORING_LIMIT},
                },
            },
        },
    }
    return [
        {
            "namespace": "chartdex",
            "name": "get_authoring_capabilities",
            "description": "Describe the draft dashboard and panel specs Codex is allowed to create.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": "chartdex",
            "name": "validate_panel_spec",
            "description": "Validate a draft panel spec before creating it and return actionable repair feedback.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["panel"],
                "properties": {"panel": panel_schema},
            },
            "exposeToContext": True,
        },
        {
            "namespace": "chartdex",
            "name": "create_draft_dashboard",
            "description": (
                "Create a personal draft dashboard owned by the current user. Optional panels are validated "
                "and created as draft panels. This cannot create org dashboards."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "description"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "panels": {"type": "array", "items": panel_schema},
                },
            },
            "exposeToContext": True,
        },
        {
            "namespace": "chartdex",
            "name": "create_draft_panel",
            "description": "Create a draft panel on the current user's personal dashboard after validating the spec.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dashboard_id", "panel"],
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "panel": panel_schema,
                },
            },
            "exposeToContext": True,
        },
    ]


async def handle_authoring_tool_call(context: "ChartDexToolContext", tool: str, arguments: Any) -> str | None:
    if tool == "get_authoring_capabilities":
        ensure_arguments(arguments, set())
        return authoring_json(get_authoring_capabilities(context))
    if tool == "validate_panel_spec":
        arguments = require_object(arguments)
        ensure_arguments(arguments, {"panel"})
        return authoring_json(validate_panel_spec(context, arguments.get("panel")))
    if tool == "create_draft_dashboard":
        arguments = require_object(arguments)
        ensure_arguments(arguments, {"name", "description", "panels"})
        return authoring_json(create_draft_dashboard_from_args(context, arguments))
    if tool == "create_draft_panel":
        arguments = require_object(arguments)
        ensure_arguments(arguments, {"dashboard_id", "panel"})
        return authoring_json(create_draft_panel_from_args(context, arguments))
    return None


def get_authoring_capabilities(context: "ChartDexToolContext") -> dict[str, object]:
    provider = get_metrics_provider_for_org(context.app_db_path, context.org_id)
    dimensions = provider.list_dimensions()
    metrics = provider.list_metric_catalog()
    personal_dashboards = list_dashboards(
        context.app_db_path,
        org_id=context.org_id,
        space="personal",
        owner_user_id=context.user_id,
    )
    return {
        "policy": {
            "writes": "Codex can create only personal draft dashboards and panels owned by the current user.",
            "publish_to_org": False,
            "raw_sql": False,
        },
        "panel_types": sorted(ALLOWED_PANEL_TYPES),
        "value_formats": sorted(ALLOWED_VALUE_FORMATS),
        "metrics": metrics,
        "dimensions": dimensions,
        "writable_dashboards": personal_dashboards,
        "rules": [
            "Use validate_panel_spec before create_draft_panel or create_draft_dashboard.",
            "Use exactly one metric per authored panel.",
            "Line panels must use granularity 'day' and dimensions ['date'].",
            "Bar panels must use granularity 'none' and exactly one non-date dimension.",
            "Filters support only '=' and 'in' operators.",
        ],
        "examples": {
            "line_panel": valid_line_example(),
            "bar_panel": valid_bar_example(),
        },
    }


def validate_panel_spec(context: "ChartDexToolContext", raw_panel: Any) -> dict[str, object]:
    provider = get_metrics_provider_for_org(context.app_db_path, context.org_id)
    normalized, issues = normalize_panel_spec(provider, raw_panel)
    if issues:
        return invalid_result(issues)
    try:
        provider.query_metrics(normalized["query"])
    except Exception as exc:
        return invalid_result([ValidationIssue("query", str(exc))])
    return {"valid": True, "panel": normalized, "preview": {"query_rows_available": True}}


def create_draft_dashboard_from_args(context: "ChartDexToolContext", arguments: dict[str, object]) -> dict[str, object]:
    name = bounded_string(arguments, "name", 120)
    description = bounded_string(arguments, "description", 500)
    panels = arguments.get("panels") or []
    if not isinstance(panels, list):
        raise ValueError("panels must be a list")
    normalized_panels = validated_panels_or_raise(context, panels)
    dashboard = create_draft_dashboard(
        context.app_db_path,
        org_id=context.org_id,
        user_id=context.user_id,
        name=name,
        description=description,
        source_thread_id=context.thread_id,
    )
    created_panels = [
        create_draft_panel(
            context.app_db_path,
            org_id=context.org_id,
            user_id=context.user_id,
            dashboard_id=str(dashboard["id"]),
            panel=panel,
            source_thread_id=context.thread_id,
        )
        for panel in normalized_panels
    ]
    detail = get_dashboard_detail(
        context.app_db_path,
        dashboard_id=str(dashboard["id"]),
        org_id=context.org_id,
        user_id=context.user_id,
    )
    return {"dashboard": dashboard, "detail": detail, "panels": created_panels}


def create_draft_panel_from_args(context: "ChartDexToolContext", arguments: dict[str, object]) -> dict[str, object]:
    dashboard_id = bounded_string(arguments, "dashboard_id", 120)
    normalized_panels = validated_panels_or_raise(context, [arguments.get("panel")])
    panel = create_draft_panel(
        context.app_db_path,
        org_id=context.org_id,
        user_id=context.user_id,
        dashboard_id=dashboard_id,
        panel=normalized_panels[0],
        source_thread_id=context.thread_id,
    )
    detail = get_dashboard_detail(
        context.app_db_path,
        dashboard_id=dashboard_id,
        org_id=context.org_id,
        user_id=context.user_id,
    )
    return {"panel": panel, "dashboard": detail}


def validated_panels_or_raise(context: "ChartDexToolContext", panels: list[object]) -> list[dict[str, object]]:
    normalized_panels = []
    for index, panel in enumerate(panels):
        result = validate_panel_spec(context, panel)
        if not result["valid"]:
            raise ValueError(f"Panel {index} is invalid: {json.dumps(result['errors'], sort_keys=True)}")
        normalized_panels.append(result["panel"])
    return normalized_panels


def normalize_panel_spec(provider: object, raw_panel: Any) -> tuple[dict[str, object], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    if not isinstance(raw_panel, dict):
        return {}, [ValidationIssue("panel", "panel must be an object")]
    ensure_no_unknown(raw_panel, {"title", "type", "value_format", "description", "query"}, "panel", issues)
    panel_type = string_field(raw_panel, "type", "panel.type", issues)
    title = string_field(raw_panel, "title", "panel.title", issues, max_length=120)
    description = string_field(raw_panel, "description", "panel.description", issues, max_length=500)
    value_format = string_field(raw_panel, "value_format", "panel.value_format", issues)
    if panel_type and panel_type not in ALLOWED_PANEL_TYPES:
        issues.append(ValidationIssue("panel.type", "Use one of: bar, line"))
    if value_format and value_format not in ALLOWED_VALUE_FORMATS:
        issues.append(ValidationIssue("panel.value_format", "Use one of: currency, integer, percent"))

    query = raw_panel.get("query")
    normalized_query, metric_key, query_issues = normalize_query_spec(provider, panel_type, query)
    issues.extend(query_issues)
    if metric_key and value_format:
        expected = expected_format(metric_key)
        if expected and value_format != expected:
            issues.append(
                ValidationIssue(
                    "panel.value_format",
                    f"Expected '{expected}' for metric '{metric_key}'.",
                )
            )
    if issues:
        return {}, issues
    return {
        "title": title,
        "type": panel_type,
        "metric_key": metric_key,
        "value_format": value_format,
        "description": description,
        "query": normalized_query,
    }, []


def normalize_query_spec(
    provider: object,
    panel_type: str | None,
    raw_query: Any,
) -> tuple[dict[str, object], str | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    if not isinstance(raw_query, dict):
        return {}, None, [ValidationIssue("panel.query", "query must be an object")]
    ensure_no_unknown(
        raw_query,
        {"metrics", "dimensions", "granularity", "start_date", "end_date", "filters", "limit"},
        "panel.query",
        issues,
    )
    metrics = string_list(raw_query, "metrics", "panel.query.metrics", issues)
    dimensions = string_list(raw_query, "dimensions", "panel.query.dimensions", issues)
    metric_key = metrics[0] if len(metrics) == 1 else None
    if len(metrics) != 1:
        issues.append(ValidationIssue("panel.query.metrics", "Use exactly one metric."))
    allowed_metrics = {
        str(metric["metric_id"])
        for metric in provider.list_metric_catalog()
        if isinstance(metric.get("metric_id"), str)
    }
    if metric_key and metric_key not in allowed_metrics:
        issues.append(
            ValidationIssue(
                "panel.query.metrics[0]",
                f"Unsupported metric '{metric_key}'. Use get_authoring_capabilities for valid metrics.",
            )
        )
    granularity = raw_query.get("granularity") or ("day" if panel_type == "line" else "none")
    if granularity not in {"none", "day"}:
        issues.append(ValidationIssue("panel.query.granularity", "Use 'none' or 'day'."))
    if panel_type == "line":
        if dimensions != ["date"]:
            issues.append(ValidationIssue("panel.query.dimensions", "Line panels must use dimensions ['date']."))
        if granularity != "day":
            issues.append(ValidationIssue("panel.query.granularity", "Line panels must use granularity 'day'."))
    if panel_type == "bar":
        if len(dimensions) != 1 or dimensions == ["date"]:
            issues.append(ValidationIssue("panel.query.dimensions", "Bar panels need exactly one non-date dimension."))
        if granularity != "none":
            issues.append(ValidationIssue("panel.query.granularity", "Bar panels must use granularity 'none'."))

    filters = normalize_filters(raw_query.get("filters") or [], issues)
    limit = raw_query.get("limit", 100)
    if not isinstance(limit, int) or limit < 1 or limit > MAX_AUTHORING_LIMIT:
        issues.append(ValidationIssue("panel.query.limit", f"limit must be an integer between 1 and {MAX_AUTHORING_LIMIT}."))
        limit = 100
    normalized: dict[str, object] = {
        "metrics": metrics,
        "dimensions": dimensions,
        "granularity": granularity,
        "filters": filters,
        "limit": limit,
    }
    for field in ("start_date", "end_date"):
        value = raw_query.get(field)
        if value is not None:
            if not isinstance(value, str) or not value:
                issues.append(ValidationIssue(f"panel.query.{field}", f"{field} must be a YYYY-MM-DD string."))
            else:
                normalized[field] = value
    return normalized, metric_key, issues


def normalize_filters(raw_filters: Any, issues: list[ValidationIssue]) -> list[dict[str, object]]:
    if not isinstance(raw_filters, list):
        issues.append(ValidationIssue("panel.query.filters", "filters must be a list."))
        return []
    filters = []
    for index, raw_filter in enumerate(raw_filters):
        path = f"panel.query.filters[{index}]"
        if not isinstance(raw_filter, dict):
            issues.append(ValidationIssue(path, "filter must be an object."))
            continue
        ensure_no_unknown(raw_filter, {"field", "op", "value"}, path, issues)
        field = raw_filter.get("field")
        if not isinstance(field, str) or not field:
            issues.append(ValidationIssue(f"{path}.field", "field is required."))
            continue
        op = str(raw_filter.get("op") or "=").lower()
        if op not in ALLOWED_FILTER_OPERATORS:
            issues.append(ValidationIssue(f"{path}.op", "Use '=' or 'in'."))
            continue
        value = raw_filter.get("value")
        if op == "=" and isinstance(value, (list, dict)):
            issues.append(ValidationIssue(f"{path}.value", "'=' filters require a scalar value."))
            continue
        if op == "in" and (not isinstance(value, list) or not value):
            issues.append(ValidationIssue(f"{path}.value", "'in' filters require a non-empty value list."))
            continue
        if op == "in" and any(isinstance(item, (list, dict)) for item in value):
            issues.append(ValidationIssue(f"{path}.value", "'in' filter values must be scalar values."))
            continue
        filters.append({"field": field, "op": op, "value": value})
    return filters


def invalid_result(issues: list[ValidationIssue]) -> dict[str, object]:
    return {
        "valid": False,
        "errors": [issue.as_dict() for issue in issues],
        "corrected_examples": {
            "line_panel": valid_line_example(),
            "bar_panel": valid_bar_example(),
        },
    }


def expected_format(metric_key: str) -> str | None:
    if metric_key in {"revenue", "refund_amount", "average_order_value"}:
        return "currency"
    if "rate" in metric_key or "conversion" in metric_key:
        return "percent"
    return "integer"


def ensure_arguments(arguments: Any, allowed: set[str]) -> dict[str, object]:
    arguments = require_object(arguments)
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"Unsupported tool arguments: {', '.join(sorted(unknown))}")
    return arguments


def require_object(arguments: Any) -> dict[str, object]:
    if arguments is None:
        return {}
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    return arguments


def ensure_no_unknown(value: dict[str, object], allowed: set[str], path: str, issues: list[ValidationIssue]) -> None:
    unknown = set(value) - allowed
    if unknown:
        message = f"Unsupported fields: {', '.join(sorted(unknown))}."
        if issues is not None:
            issues.append(ValidationIssue(path, message))
        else:
            raise ValueError(message)


def string_field(
    value: dict[str, object],
    key: str,
    path: str,
    issues: list[ValidationIssue],
    max_length: int = 80,
) -> str | None:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        issues.append(ValidationIssue(path, f"{key} is required."))
        return None
    stripped = raw.strip()
    if len(stripped) > max_length:
        issues.append(ValidationIssue(path, f"{key} must be {max_length} characters or fewer."))
    return stripped


def bounded_string(arguments: dict[str, object], key: str, max_length: int) -> str:
    issues: list[ValidationIssue] = []
    value = string_field(arguments, key, key, issues, max_length=max_length)
    if issues:
        raise ValueError(json.dumps([issue.as_dict() for issue in issues], sort_keys=True))
    return str(value)


def string_list(value: dict[str, object], key: str, path: str, issues: list[ValidationIssue]) -> list[str]:
    raw = value.get(key)
    if not isinstance(raw, list):
        issues.append(ValidationIssue(path, f"{key} must be a list."))
        return []
    strings = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item:
            issues.append(ValidationIssue(f"{path}[{index}]", "Expected a non-empty string."))
        else:
            strings.append(item)
    return strings


def authoring_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def valid_line_example() -> dict[str, object]:
    return {
        "title": "Android Checkout Conversion",
        "type": "line",
        "value_format": "percent",
        "description": "Daily checkout conversion for Android sessions.",
        "query": {
            "metrics": ["checkout_conversion"],
            "dimensions": ["date"],
            "filters": [{"field": "platform", "op": "=", "value": "android"}],
            "granularity": "day",
            "limit": 100,
        },
    }


def valid_bar_example() -> dict[str, object]:
    return {
        "title": "Checkout Conversion by Promo Code",
        "type": "bar",
        "value_format": "percent",
        "description": "Checkout conversion grouped by promo code.",
        "query": {
            "metrics": ["checkout_conversion"],
            "dimensions": ["promo_code"],
            "filters": [{"field": "platform", "op": "=", "value": "android"}],
            "granularity": "none",
            "limit": 20,
        },
    }
