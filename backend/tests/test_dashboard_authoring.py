import json
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from app.codex_tools import ChartDexToolContext, dynamic_tool_specs, handle_tool_call
from app.database import get_dashboard_detail, list_dashboards
from app.main import app
from app.settings import get_settings


@pytest.fixture
def initialized_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    app_db_path = tmp_path / "app_state.sqlite3"
    monkeypatch.setenv("CHARTDEX_APP_DB_PATH", str(app_db_path))
    monkeypatch.setenv("CHARTDEX_METRICS_DB_PATH", str(tmp_path / "metrics.sqlite3"))
    get_settings.cache_clear()
    with TestClient(app):
        yield app_db_path
    get_settings.cache_clear()


def test_dynamic_tool_specs_include_authoring_tools() -> None:
    chartdex_tools = [tool for tool in dynamic_tool_specs() if tool["namespace"] == "chartdex"]

    assert {
        "get_authoring_capabilities",
        "validate_panel_spec",
        "create_draft_dashboard",
        "create_draft_panel",
    }.issubset({tool["name"] for tool in chartdex_tools})


def test_authoring_capabilities_describe_allowed_write_surface(initialized_app: Path) -> None:
    context = tool_context(initialized_app)

    result = json.loads(anyio.run(handle_tool_call, context, "chartdex", "get_authoring_capabilities", {}))

    assert result["policy"]["publish_to_org"] is False
    assert result["policy"]["raw_sql"] is False
    assert result["panel_types"] == ["bar", "line"]
    assert "checkout_conversion" in {metric["metric_id"] for metric in result["metrics"]}
    assert {dashboard["name"] for dashboard in result["writable_dashboards"]} == {
        "A/B Test Results",
        "Growth Experiments",
    }


def test_validate_panel_spec_returns_field_level_errors(initialized_app: Path) -> None:
    context = tool_context(initialized_app)
    panel = {
        **valid_line_panel(),
        "query": {
            **valid_line_panel()["query"],
            "metrics": ["not_a_metric"],
        },
    }

    result = json.loads(anyio.run(handle_tool_call, context, "chartdex", "validate_panel_spec", {"panel": panel}))

    assert result["valid"] is False
    assert any(error["path"] == "panel.query.metrics[0]" for error in result["errors"])
    assert "line_panel" in result["corrected_examples"]


def test_create_draft_dashboard_persists_renderable_panel(initialized_app: Path) -> None:
    context = tool_context(initialized_app)

    result = json.loads(
        anyio.run(
            handle_tool_call,
            context,
            "chartdex",
            "create_draft_dashboard",
            {
                "name": "Android Checkout Investigation",
                "description": "Draft analysis created by Codex for Android checkout conversion.",
                "panels": [valid_line_panel()],
            },
        )
    )

    dashboard = result["dashboard"]
    assert dashboard["space"] == "personal"
    assert dashboard["status"] == "draft"
    assert dashboard["created_by"] == "codex"
    assert dashboard["owner_user_id"] == "u_admin"
    assert result["panels"][0]["metric_key"] == "checkout_conversion"

    detail = get_dashboard_detail(
        initialized_app,
        dashboard_id=dashboard["id"],
        org_id="org_acme",
        user_id="u_admin",
    )
    assert detail is not None
    assert [panel["title"] for panel in detail["panels"]] == ["Android Checkout Conversion"]
    assert detail["panels"][0]["type"] == "line"
    assert detail["panels"][0]["data"][0]["observed_on"] == "2026-05-01"

    personal_dashboards = list_dashboards(
        initialized_app,
        org_id="org_acme",
        space="personal",
        owner_user_id="u_admin",
    )
    assert "Android Checkout Investigation" in {dashboard["name"] for dashboard in personal_dashboards}


def test_create_draft_panel_rejects_org_dashboard(initialized_app: Path) -> None:
    context = tool_context(initialized_app)

    with pytest.raises(ValueError, match="personal dashboards"):
        anyio.run(
            handle_tool_call,
            context,
            "chartdex",
            "create_draft_panel",
            {
                "dashboard_id": "dash_checkout_funnel",
                "panel": valid_line_panel(),
            },
        )


def tool_context(app_db_path: Path) -> ChartDexToolContext:
    return ChartDexToolContext(
        app_db_path=app_db_path,
        org_id="org_acme",
        user_id="u_admin",
        thread_id="thread_authoring_test",
    )


def valid_line_panel() -> dict[str, object]:
    return {
        "title": "Android Checkout Conversion",
        "type": "line",
        "value_format": "percent",
        "description": "Daily checkout conversion across the investigated period.",
        "query": {
            "metrics": ["checkout_conversion"],
            "dimensions": ["date"],
            "granularity": "day",
            "start_date": "2026-05-01",
            "end_date": "2026-05-18",
            "limit": 100,
        },
    }
