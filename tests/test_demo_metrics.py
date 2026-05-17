from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sqlite3
import sys
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_demo_metrics.py"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_demo_metrics", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, object]]:
    generator = load_generator()
    out_path = tmp_path_factory.mktemp("demo_metrics") / "chartdex_demo.sqlite"
    summary = generator.generate_database(
        out_path,
        days=180,
        seed=42,
        end_date=date(2026, 5, 18),
    )
    return out_path, summary


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def test_generator_creates_required_tables_and_views(demo_db: tuple[Path, dict[str, object]]) -> None:
    db_path, summary = demo_db

    assert db_path.exists()
    assert summary["row_count"] > 20_000
    assert summary["start_date"] == "2025-11-20"
    assert summary["end_date"] == "2026-05-18"

    with connect(db_path) as connection:
        objects = {
            row["name"]: row["type"]
            for row in connection.execute(
                """
                SELECT name, type
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                """
            )
        }

    assert objects["metric_facts_daily"] == "table"
    assert objects["metric_catalog"] == "table"
    assert objects["business_events"] == "table"
    assert objects["experiments"] == "table"
    assert objects["ui_metric_mapping"] == "table"
    assert objects["seed_dashboards"] == "table"
    assert objects["v_daily_overview"] == "view"
    assert objects["v_checkout_by_platform"] == "view"
    assert objects["v_experiment_rollout"] == "view"
    assert objects["v_promo_performance"] == "view"
    assert objects["v_hidden_bug_slice"] == "view"


def test_metadata_supports_demo_story(demo_db: tuple[Path, dict[str, object]]) -> None:
    db_path, _summary = demo_db

    with connect(db_path) as connection:
        metrics = {
            row["metric_id"]: row
            for row in connection.execute(
                "SELECT * FROM metric_catalog WHERE metric_id IN (?, ?, ?)",
                ("checkout_conversion", "payment_error_rate", "promo_success_rate"),
            )
        }
        dashboard_titles = [
            row["title"] for row in connection.execute("SELECT title FROM seed_dashboards ORDER BY title")
        ]
        bug_event = connection.execute(
            "SELECT * FROM business_events WHERE id = 'BUG-1772'"
        ).fetchone()
        experiments = {
            row["experiment_id"]: row["status"]
            for row in connection.execute("SELECT experiment_id, status FROM experiments")
        }

    assert set(metrics) == {
        "checkout_conversion",
        "payment_error_rate",
        "promo_success_rate",
    }
    assert metrics["checkout_conversion"]["formula"] == "purchases / checkout_started"
    assert dashboard_titles == [
        "Campaign Performance",
        "Checkout Funnel",
        "Revenue Overview",
    ]
    assert bug_event is not None
    assert "not known to the app user" in bug_event["demo_hint"]
    assert experiments == {
        "EXP-001": "completed",
        "EXP-002": "completed",
        "EXP-003": "active",
    }


def test_smoke_summary_proves_hidden_bug_is_discoverable(
    demo_db: tuple[Path, dict[str, object]],
) -> None:
    _db_path, summary = demo_db

    assert summary["hidden_bug_checkout_conversion_drop"] >= 0.40
    assert summary["hidden_bug_promo_error_lift"] >= 2.0
    assert summary["hidden_bug_payment_error_lift"] >= 1.0
    assert 0.01 <= summary["global_checkout_conversion_dip"] <= 0.05
    assert summary["android_checkout_v2_treatment_dip"] >= 0.07
    assert abs(summary["ios_checkout_v2_treatment_change"]) <= 0.05
    assert summary["checkout_v2_pre_bug_treatment_lift"] >= 0.025


def test_hidden_bug_view_is_narrow_and_material(demo_db: tuple[Path, dict[str, object]]) -> None:
    db_path, _summary = demo_db

    with connect(db_path) as connection:
        hidden = connection.execute(
            """
            SELECT
                SUM(checkout_started) AS checkout_started,
                SUM(purchases) AS purchases,
                SUM(promo_errors) AS promo_errors,
                SUM(payment_errors) AS payment_errors
            FROM v_hidden_bug_slice
            WHERE date BETWEEN '2026-05-10' AND '2026-05-18'
            """
        ).fetchone()
        global_last = connection.execute(
            """
            SELECT
                SUM(checkout_started) AS checkout_started,
                SUM(purchases) AS purchases
            FROM v_daily_overview
            WHERE date BETWEEN '2026-05-10' AND '2026-05-18'
            """
        ).fetchone()
        unaffected_android = connection.execute(
            """
            SELECT
                CAST(SUM(purchases) AS REAL) / SUM(checkout_started) AS checkout_conversion
            FROM metric_facts_daily
            WHERE date BETWEEN '2026-05-10' AND '2026-05-18'
              AND platform = 'android_app'
              AND checkout_variant = 'checkout_v2_treatment'
              AND NOT (
                promo_code = 'FROST20'
                AND cart_size_bucket = '3_plus_items'
                AND cart_weight_bucket = 'heavy'
              )
            """
        ).fetchone()

    assert hidden["checkout_started"] > 1_000
    assert hidden["purchases"] / hidden["checkout_started"] < 0.30
    assert hidden["promo_errors"] > 300
    assert hidden["payment_errors"] > 120
    assert hidden["checkout_started"] / global_last["checkout_started"] < 0.08
    assert global_last["purchases"] / global_last["checkout_started"] > 0.66
    assert unaffected_android["checkout_conversion"] > 0.68


def test_generation_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    generator = load_generator()
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"

    first_summary = generator.generate_database(
        first,
        days=180,
        seed=42,
        end_date=date(2026, 5, 18),
    )
    second_summary = generator.generate_database(
        second,
        days=180,
        seed=42,
        end_date=date(2026, 5, 18),
    )

    assert first_summary["row_count"] == second_summary["row_count"]
    assert first_summary["hidden_bug_checkout_conversion_drop"] == second_summary[
        "hidden_bug_checkout_conversion_drop"
    ]

    with connect(first) as first_connection, connect(second) as second_connection:
        first_totals = first_connection.execute(
            """
            SELECT SUM(sessions), SUM(purchases), SUM(revenue_cents), SUM(payment_errors)
            FROM metric_facts_daily
            """
        ).fetchone()
        second_totals = second_connection.execute(
            """
            SELECT SUM(sessions), SUM(purchases), SUM(revenue_cents), SUM(payment_errors)
            FROM metric_facts_daily
            """
        ).fetchone()

    assert tuple(first_totals) == tuple(second_totals)
