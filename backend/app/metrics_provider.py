from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol


class MetricsProvider(Protocol):
    def list_seed_dashboards(self) -> list[dict[str, object]]:
        ...

    def get_dashboard_detail(self, dashboard: dict[str, object]) -> dict[str, object]:
        ...

    def list_metric_points(self, metric: str) -> list[dict[str, object]]:
        ...


class SQLiteMetricsProvider:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def list_seed_dashboards(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, space, title, description, panels_json
                FROM seed_dashboards
                ORDER BY
                    CASE id
                        WHEN 'dash_revenue_overview' THEN 1
                        WHEN 'dash_checkout_funnel' THEN 2
                        WHEN 'dash_campaign_performance' THEN 3
                        ELSE 100
                    END,
                    title
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_dashboard_detail(self, dashboard: dict[str, object]) -> dict[str, object]:
        slug = str(dashboard["slug"])
        return {
            **dashboard,
            "agent_description": dashboard.get("agent_description", dashboard["description"]),
            "time_range_label": self.time_range_label(),
            "panels": self._panels_for_dashboard(slug),
        }

    def list_metric_points(self, metric: str) -> list[dict[str, object]]:
        if metric == "revenue":
            return self._daily_series("revenue", "revenue_cents / 100.0")
        if metric in {"conversion", "checkout_conversion"}:
            return self._daily_series("conversion", "checkout_conversion * 100.0")
        if metric == "sessions":
            return self._daily_series("sessions", "sessions")
        raise ValueError(f"Unsupported metric: {metric}")

    def time_range_label(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MIN(date) AS start_date, MAX(date) AS end_date
                FROM v_daily_overview
                WHERE date >= date((SELECT MAX(date) FROM v_daily_overview), '-29 days')
                """
            ).fetchone()
        return f"{row['start_date']} - {row['end_date']}"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _panels_for_dashboard(self, slug: str) -> list[dict[str, object]]:
        if slug == "checkout-funnel":
            return [
                self._funnel_panel(),
                self._line_panel(
                    "panel_checkout_conversion",
                    "Checkout Conversion Over Time",
                    "checkout_conversion",
                    "checkout_conversion * 100.0",
                    "percent",
                ),
                self._bar_panel(
                    "panel_payment_error_by_platform",
                    "Payment Error Rate by Platform",
                    "payment_error_rate_by_platform",
                    "percent",
                    """
                    SELECT
                        platform AS label,
                        CASE WHEN SUM(payment_started) = 0 THEN 0.0
                             ELSE CAST(SUM(payment_errors) AS REAL) / SUM(payment_started) * 100.0
                        END AS value
                    FROM metric_facts_daily
                    WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                    GROUP BY platform
                    ORDER BY value DESC
                    """,
                ),
                self._bar_panel(
                    "panel_promo_success_by_code",
                    "Promo Success Rate by Code",
                    "promo_success_rate_by_code",
                    "percent",
                    """
                    SELECT
                        promo_code AS label,
                        CASE WHEN SUM(promo_attempts) = 0 THEN 0.0
                             ELSE CAST(SUM(promo_success) AS REAL) / SUM(promo_attempts) * 100.0
                        END AS value
                    FROM metric_facts_daily
                    WHERE promo_code <> 'none'
                      AND date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                    GROUP BY promo_code
                    ORDER BY value DESC
                    """,
                ),
            ]
        if slug == "campaign-performance":
            return [
                self._bar_panel(
                    "panel_revenue_by_channel",
                    "Revenue by Channel",
                    "revenue_by_channel",
                    "currency",
                    """
                    SELECT channel AS label, SUM(revenue_cents) / 100.0 AS value
                    FROM metric_facts_daily
                    WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                    GROUP BY channel
                    ORDER BY value DESC
                    """,
                ),
                self._bar_panel(
                    "panel_sessions_by_channel",
                    "Sessions by Channel",
                    "sessions_by_channel",
                    "integer",
                    """
                    SELECT channel AS label, SUM(sessions) AS value
                    FROM metric_facts_daily
                    WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                    GROUP BY channel
                    ORDER BY value DESC
                    """,
                ),
                self._bar_panel(
                    "panel_conversion_by_channel",
                    "Conversion by Channel",
                    "conversion_by_channel",
                    "percent",
                    """
                    SELECT
                        channel AS label,
                        CASE WHEN SUM(sessions) = 0 THEN 0.0
                             ELSE CAST(SUM(purchases) AS REAL) / SUM(sessions) * 100.0
                        END AS value
                    FROM metric_facts_daily
                    WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                    GROUP BY channel
                    ORDER BY value DESC
                    """,
                ),
                self._bar_panel(
                    "panel_promo_revenue_by_code",
                    "Promo Revenue by Code",
                    "promo_revenue_by_code",
                    "currency",
                    """
                    SELECT promo_code AS label, SUM(revenue_cents) / 100.0 AS value
                    FROM metric_facts_daily
                    WHERE promo_code <> 'none'
                      AND date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                    GROUP BY promo_code
                    ORDER BY value DESC
                    """,
                ),
            ]
        return [
            self._line_panel(
                "panel_revenue_over_time",
                "Revenue Over Time",
                "revenue",
                "revenue_cents / 100.0",
                "currency",
            ),
            self._line_panel(
                "panel_sessions_over_time",
                "Sessions Over Time",
                "sessions",
                "sessions",
                "integer",
            ),
            self._line_panel(
                "panel_average_order_value",
                "Average Order Value Over Time",
                "average_order_value",
                "average_order_value_cents / 100.0",
                "currency",
            ),
            self._bar_panel(
                "panel_purchases_by_platform",
                "Purchases by Platform",
                "purchases_by_platform",
                "integer",
                """
                SELECT platform AS label, SUM(purchases) AS value
                FROM metric_facts_daily
                WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                GROUP BY platform
                ORDER BY value DESC
                """,
            ),
        ]

    def _line_panel(
        self,
        panel_id: str,
        title: str,
        metric_key: str,
        expression: str,
        value_format: str,
    ) -> dict[str, object]:
        return {
            "id": panel_id,
            "title": title,
            "type": "line",
            "metric_key": metric_key,
            "value_format": value_format,
            "description": panel_description(panel_id),
            "agent_description": panel_agent_description(panel_id),
            "data": self._daily_series(metric_key, expression),
        }

    def _daily_series(self, metric: str, expression: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    date AS observed_on,
                    ? AS metric,
                    {expression} AS value
                FROM v_daily_overview
                WHERE date >= date((SELECT MAX(date) FROM v_daily_overview), '-29 days')
                ORDER BY date
                """,
                (metric,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _bar_panel(
        self,
        panel_id: str,
        title: str,
        metric_key: str,
        value_format: str,
        query: str,
    ) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return {
            "id": panel_id,
            "title": title,
            "type": "bar",
            "metric_key": metric_key,
            "value_format": value_format,
            "description": panel_description(panel_id),
            "agent_description": panel_agent_description(panel_id),
            "data": [dict(row) for row in rows],
        }

    def _funnel_panel(self) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    SUM(sessions) AS sessions,
                    SUM(product_views) AS product_views,
                    SUM(add_to_cart) AS add_to_cart,
                    SUM(checkout_started) AS checkout_started,
                    SUM(payment_started) AS payment_started,
                    SUM(purchases) AS purchases
                FROM metric_facts_daily
                WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
                """
            ).fetchone()
        sessions = row["sessions"] or 0
        steps = [
            ("Sessions", sessions),
            ("Product Views", row["product_views"] or 0),
            ("Added to Cart", row["add_to_cart"] or 0),
            ("Checkout Started", row["checkout_started"] or 0),
            ("Payment Started", row["payment_started"] or 0),
            ("Purchases", row["purchases"] or 0),
        ]
        return {
            "id": "panel_checkout_funnel",
            "title": "Checkout Funnel",
            "type": "funnel",
            "metric_key": "checkout_funnel",
            "value_format": "integer",
            "description": panel_description("panel_checkout_funnel"),
            "agent_description": panel_agent_description("panel_checkout_funnel"),
            "data": [
                {
                    "label": label,
                    "value": value,
                    "rate": round((value / sessions) * 100, 1) if sessions else None,
                }
                for label, value in steps
            ],
        }


def get_metrics_provider_for_org(app_db_path: Path, org_id: str) -> MetricsProvider:
    with sqlite3.connect(app_db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT provider_type, config_json
            FROM org_metric_providers
            WHERE org_id = ?
            """,
            (org_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"No metrics provider configured for org {org_id}")
    provider_type = row["provider_type"]
    config = json.loads(row["config_json"])
    if provider_type == "sqlite":
        return SQLiteMetricsProvider(Path(config["db_path"]))
    raise RuntimeError(f"Unsupported metrics provider type: {provider_type}")


PANEL_DESCRIPTIONS = {
    "panel_checkout_funnel": "Counts and rates for each checkout step in the latest 30-day window.",
    "panel_checkout_conversion": "Daily session-to-purchase conversion rate for the checkout funnel.",
    "panel_payment_error_by_platform": "Payment error rate by platform in the latest 30-day window.",
    "panel_promo_success_by_code": "Promo-code validation success rate by promo code.",
    "panel_revenue_by_channel": "Revenue contribution by marketing channel.",
    "panel_sessions_by_channel": "Session volume by marketing channel.",
    "panel_conversion_by_channel": "Purchase conversion rate by marketing channel.",
    "panel_promo_revenue_by_code": "Revenue associated with each promo code.",
    "panel_revenue_over_time": "Daily revenue for the latest 30-day window.",
    "panel_sessions_over_time": "Daily session volume for the latest 30-day window.",
    "panel_average_order_value": "Daily average order value for completed purchases.",
    "panel_purchases_by_platform": "Completed purchases grouped by web, iOS, and Android.",
}


PANEL_AGENT_DESCRIPTIONS = {
    "panel_checkout_funnel": (
        "Use this panel when the user asks where checkout drop-off happens. It compares total sessions, product views, "
        "cart additions, checkout starts, payment starts, and completed purchases, with each step's rate relative to sessions."
    ),
    "panel_checkout_conversion": (
        "Use this time-series panel for questions about checkout conversion changes, dips, spikes, and selected date ranges. "
        "It is the primary panel for investigating conversion anomalies such as an Android checkout drop around a specific week."
    ),
    "panel_payment_error_by_platform": (
        "Use this panel to compare payment reliability across web, iOS, and Android. It is useful when conversion movement "
        "may be caused by payment failures or platform-specific checkout defects."
    ),
    "panel_promo_success_by_code": (
        "Use this panel when the user asks about promo-code failures, coupon validation issues, or whether a code is blocking checkout."
    ),
    "panel_revenue_by_channel": (
        "Use this panel to identify which acquisition channels are contributing the most revenue in the latest dashboard window."
    ),
    "panel_sessions_by_channel": (
        "Use this panel to compare traffic volume by acquisition channel and separate traffic changes from conversion or order-value changes."
    ),
    "panel_conversion_by_channel": (
        "Use this panel to compare channel quality by purchase conversion rate, especially when revenue moved but traffic did not."
    ),
    "panel_promo_revenue_by_code": (
        "Use this panel to understand which promo codes are associated with revenue and whether promotions are influencing campaign performance."
    ),
    "panel_revenue_over_time": (
        "Use this time-series panel for top-line revenue trend questions, date-range selections, and investigations into revenue dips or spikes."
    ),
    "panel_sessions_over_time": (
        "Use this time-series panel for traffic trend questions and for deciding whether revenue changes came from session volume."
    ),
    "panel_average_order_value": (
        "Use this time-series panel when the user asks whether basket size or order value changed over time."
    ),
    "panel_purchases_by_platform": (
        "Use this panel to compare completed purchase volume by platform and spot whether one platform is over- or under-performing."
    ),
}


def panel_description(panel_id: str) -> str:
    return PANEL_DESCRIPTIONS[panel_id]


def panel_agent_description(panel_id: str) -> str:
    return PANEL_AGENT_DESCRIPTIONS[panel_id]
