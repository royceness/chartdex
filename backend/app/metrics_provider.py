from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Protocol


class MetricsProvider(Protocol):
    def list_seed_dashboards(self) -> list[dict[str, object]]:
        ...

    def get_dashboard_detail(self, dashboard: dict[str, object]) -> dict[str, object]:
        ...

    def list_metric_points(self, metric: str) -> list[dict[str, object]]:
        ...

    def list_metric_catalog(self) -> list[dict[str, object]]:
        ...

    def describe_metric(self, metric_id: str) -> dict[str, object] | None:
        ...

    def list_dimensions(self) -> list[dict[str, object]]:
        ...

    def list_business_events(self) -> list[dict[str, object]]:
        ...

    def list_experiments(self) -> list[dict[str, object]]:
        ...

    def query_metrics(self, query: dict[str, object]) -> list[dict[str, object]]:
        ...


class SQLiteMetricsProvider:
    max_query_days = 120
    allowed_dimensions = {
        "date",
        "platform",
        "channel",
        "region",
        "customer_segment",
        "product_category",
        "cart_size_bucket",
        "cart_weight_bucket",
        "promo_code",
        "checkout_variant",
    }
    metric_expressions = {
        "sessions": "SUM(sessions)",
        "product_views": "SUM(product_views)",
        "add_to_cart": "SUM(add_to_cart)",
        "cart_views": "SUM(cart_views)",
        "checkout_started": "SUM(checkout_started)",
        "shipping_submitted": "SUM(shipping_submitted)",
        "promo_attempts": "SUM(promo_attempts)",
        "promo_success": "SUM(promo_success)",
        "promo_errors": "SUM(promo_errors)",
        "payment_started": "SUM(payment_started)",
        "payment_errors": "SUM(payment_errors)",
        "purchases": "SUM(purchases)",
        "refunds": "SUM(refunds)",
        "revenue": "SUM(revenue_cents) / 100.0",
        "refund_amount": "SUM(refund_amount_cents) / 100.0",
        "checkout_conversion": (
            "CASE WHEN SUM(checkout_started) = 0 THEN 0.0 "
            "ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started) END"
        ),
        "overall_conversion": (
            "CASE WHEN SUM(sessions) = 0 THEN 0.0 "
            "ELSE CAST(SUM(purchases) AS REAL) / SUM(sessions) END"
        ),
        "payment_error_rate": (
            "CASE WHEN SUM(payment_started) = 0 THEN 0.0 "
            "ELSE CAST(SUM(payment_errors) AS REAL) / SUM(payment_started) END"
        ),
        "average_order_value": (
            "CASE WHEN SUM(purchases) = 0 THEN 0.0 "
            "ELSE SUM(revenue_cents) / 100.0 / SUM(purchases) END"
        ),
        "product_view_rate": (
            "CASE WHEN SUM(sessions) = 0 THEN 0.0 "
            "ELSE CAST(SUM(product_views) AS REAL) / SUM(sessions) END"
        ),
        "add_to_cart_rate": (
            "CASE WHEN SUM(product_views) = 0 THEN 0.0 "
            "ELSE CAST(SUM(add_to_cart) AS REAL) / SUM(product_views) END"
        ),
        "promo_success_rate": (
            "CASE WHEN SUM(promo_attempts) = 0 THEN 0.0 "
            "ELSE CAST(SUM(promo_success) AS REAL) / SUM(promo_attempts) END"
        ),
        "promo_error_rate": (
            "CASE WHEN SUM(promo_attempts) = 0 THEN 0.0 "
            "ELSE CAST(SUM(promo_errors) AS REAL) / SUM(promo_attempts) END"
        ),
        "refund_rate": (
            "CASE WHEN SUM(purchases) = 0 THEN 0.0 "
            "ELSE CAST(SUM(refunds) AS REAL) / SUM(purchases) END"
        ),
    }

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

    def list_metric_catalog(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    metric_id,
                    display_name,
                    formula,
                    description,
                    ui_location,
                    good_for,
                    common_failure_modes,
                    recommended_breakdowns
                FROM metric_catalog
                ORDER BY metric_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def describe_metric(self, metric_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    metric_id,
                    display_name,
                    formula,
                    description,
                    ui_location,
                    good_for,
                    common_failure_modes,
                    recommended_breakdowns
                FROM metric_catalog
                WHERE metric_id = ?
                """,
                (metric_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_dimensions(self) -> list[dict[str, object]]:
        dimensions = [
            dimension for dimension in self.allowed_dimensions
            if dimension != "date"
        ]
        with self._connect() as connection:
            result = []
            for dimension in sorted(dimensions):
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT {dimension} AS value
                    FROM metric_facts_daily
                    ORDER BY {dimension}
                    LIMIT 100
                    """
                ).fetchall()
                result.append(
                    {
                        "dimension": dimension,
                        "values": [row["value"] for row in rows],
                    }
                )
        return result

    def list_business_events(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, name, start_date, end_date, description,
                       affected_dimensions_json, expected_impact, demo_hint
                FROM business_events
                ORDER BY start_date, id
                """
            ).fetchall()
        return [self._decode_json_fields(dict(row), "affected_dimensions_json") for row in rows]

    def list_experiments(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT experiment_id, name, start_date, end_date, status, hypothesis,
                       variants_json, rollout_notes, success_metric, guardrail_metrics
                FROM experiments
                ORDER BY start_date, experiment_id
                """
            ).fetchall()
        return [self._decode_json_fields(dict(row), "variants_json") for row in rows]

    def query_metrics(self, query: dict[str, object]) -> list[dict[str, object]]:
        metrics = self._required_string_list(query, "metrics")
        dimensions = self._optional_string_list(query, "dimensions")
        granularity = str(query.get("granularity") or "none")
        if granularity not in {"none", "day"}:
            raise ValueError("granularity must be 'none' or 'day'")
        if granularity == "day" and "date" not in dimensions:
            dimensions = ["date", *dimensions]

        unknown_metrics = [metric for metric in metrics if metric not in self.metric_expressions]
        if unknown_metrics:
            raise ValueError(f"Unsupported metrics: {', '.join(unknown_metrics)}")

        unknown_dimensions = [dimension for dimension in dimensions if dimension not in self.allowed_dimensions]
        if unknown_dimensions:
            raise ValueError(f"Unsupported dimensions: {', '.join(unknown_dimensions)}")

        select_parts = [*dimensions]
        select_parts.extend(
            f"{self.metric_expressions[metric]} AS {metric}"
            for metric in metrics
        )
        where_parts, params = self._query_filters(query)
        group_by = f"GROUP BY {', '.join(dimensions)}" if dimensions else ""
        order_by = f"ORDER BY {', '.join(dimensions)}" if dimensions else ""
        limit = self._query_limit(query)

        sql = f"""
            SELECT {', '.join(select_parts)}
            FROM metric_facts_daily
            WHERE {' AND '.join(where_parts)}
            {group_by}
            {order_by}
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(sql, [*params, limit]).fetchall()
        return [dict(row) for row in rows]

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
        connection = sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _query_filters(self, query: dict[str, object]) -> tuple[list[str], list[object]]:
        self._validate_date_range(query)
        where_parts = ["date >= COALESCE(?, date((SELECT MAX(date) FROM metric_facts_daily), '-29 days'))"]
        params: list[object] = [query.get("start_date")]
        where_parts.append("date <= COALESCE(?, (SELECT MAX(date) FROM metric_facts_daily))")
        params.append(query.get("end_date"))

        filters = query.get("filters") or []
        if not isinstance(filters, list):
            raise ValueError("filters must be a list")
        for item in filters:
            if not isinstance(item, dict):
                raise ValueError("each filter must be an object")
            field = str(item.get("field") or "")
            if field not in self.allowed_dimensions or field == "date":
                raise ValueError(f"Unsupported filter field: {field}")
            op = str(item.get("op") or "=").lower()
            if op == "=":
                where_parts.append(f"{field} = ?")
                params.append(item.get("value"))
            elif op == "in":
                values = item.get("value")
                if not isinstance(values, list) or not values:
                    raise ValueError("in filters require a non-empty value list")
                where_parts.append(f"{field} IN ({', '.join('?' for _ in values)})")
                params.extend(values)
            else:
                raise ValueError(f"Unsupported filter operator: {op}")
        return where_parts, params

    def _validate_date_range(self, query: dict[str, object]) -> None:
        start_value = query.get("start_date")
        end_value = query.get("end_date")
        if start_value is None or end_value is None:
            return
        if not isinstance(start_value, str) or not isinstance(end_value, str):
            raise ValueError("start_date and end_date must be YYYY-MM-DD strings")
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        if (end - start).days > self.max_query_days:
            raise ValueError(f"date range must be {self.max_query_days} days or less")

    def _query_limit(self, query: dict[str, object]) -> int:
        raw_limit = query.get("limit", 100)
        if not isinstance(raw_limit, int):
            raise ValueError("limit must be an integer")
        if raw_limit < 1 or raw_limit > 500:
            raise ValueError("limit must be between 1 and 500")
        return raw_limit

    def _required_string_list(self, query: dict[str, object], key: str) -> list[str]:
        values = query.get(key)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{key} must be a non-empty list")
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"{key} must contain only non-empty strings")
        return values

    def _optional_string_list(self, query: dict[str, object], key: str) -> list[str]:
        values = query.get(key) or []
        if not isinstance(values, list):
            raise ValueError(f"{key} must be a list")
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"{key} must contain only non-empty strings")
        return values

    def _decode_json_fields(self, row: dict[str, object], *fields: str) -> dict[str, object]:
        for field in fields:
            value = row.get(field)
            if isinstance(value, str):
                row[field.removesuffix("_json")] = json.loads(value)
                del row[field]
        return row

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
