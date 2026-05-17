import sqlite3
from collections.abc import Iterator
from pathlib import Path

from app.auth import User, hash_password

ORG_DASHBOARDS = [
    {
        "id": "dash_revenue_overview",
        "slug": "revenue-overview",
        "name": "Revenue Overview",
        "description": "Revenue, orders, and average order value across the store.",
    },
    {
        "id": "dash_checkout_funnel",
        "slug": "checkout-funnel",
        "name": "Checkout Funnel",
        "description": "Session-to-purchase conversion and step drop-off.",
    },
    {
        "id": "dash_campaign_performance",
        "slug": "campaign-performance",
        "name": "Campaign Performance",
        "description": "Paid campaign spend, revenue, and return on ad spend.",
    },
]

PERSONAL_DASHBOARDS = [
    {
        "id": "dash_growth_experiments",
        "slug": "growth-experiments",
        "name": "Growth Experiments",
        "description": "Experiment rollout, uplift, and segment-level performance.",
        "owner_user_id": "u_admin",
    },
    {
        "id": "dash_ab_test_results",
        "slug": "ab-test-results",
        "name": "A/B Test Results",
        "description": "Personal workspace for pricing and checkout test reads.",
        "owner_user_id": "u_admin",
    },
    {
        "id": "dash_data_quality",
        "slug": "data-quality",
        "name": "Data Quality",
        "description": "Metric freshness, instrumentation gaps, and anomaly checks.",
        "owner_user_id": "u_analyst",
    },
]

DEMO_ORG = {
    "id": "org_acme",
    "name": "Acme Commerce",
}

DEMO_USERS = [
    {
        "id": "u_admin",
        "org_id": "org_acme",
        "email": "admin@acme.test",
        "name": "Avery Admin",
        "role": "admin",
        "password": "password",
    },
    {
        "id": "u_analyst",
        "org_id": "org_acme",
        "email": "analyst@acme.test",
        "name": "Riley Analyst",
        "role": "analyst",
        "password": "password",
    },
]

METRIC_SERIES = [
    ("org_acme", "revenue", "2026-05-12", 1_210_000.0),
    ("org_acme", "revenue", "2026-05-13", 1_260_000.0),
    ("org_acme", "revenue", "2026-05-14", 910_000.0),
    ("org_acme", "revenue", "2026-05-15", 820_000.0),
    ("org_acme", "revenue", "2026-05-16", 1_030_000.0),
    ("org_acme", "revenue", "2026-05-17", 880_000.0),
    ("org_acme", "revenue", "2026-05-18", 1_160_000.0),
    ("org_acme", "revenue", "2026-05-19", 1_230_000.0),
    ("org_acme", "revenue", "2026-05-20", 1_040_000.0),
    ("org_acme", "revenue", "2026-05-21", 1_060_000.0),
    ("org_acme", "revenue", "2026-05-22", 1_090_000.0),
    ("org_acme", "revenue", "2026-05-23", 1_050_000.0),
    ("org_acme", "revenue", "2026-05-24", 1_130_000.0),
    ("org_acme", "revenue", "2026-05-25", 920_000.0),
    ("org_acme", "revenue", "2026-05-26", 1_360_000.0),
    ("org_acme", "revenue", "2026-05-27", 1_520_000.0),
    ("org_acme", "revenue", "2026-05-28", 1_210_000.0),
    ("org_acme", "revenue", "2026-05-29", 1_180_000.0),
    ("org_acme", "revenue", "2026-05-30", 1_020_000.0),
    ("org_acme", "revenue", "2026-05-31", 1_170_000.0),
    ("org_acme", "revenue", "2026-06-01", 790_000.0),
    ("org_acme", "revenue", "2026-06-02", 680_000.0),
    ("org_acme", "revenue", "2026-06-03", 1_390_000.0),
    ("org_acme", "revenue", "2026-06-04", 1_280_000.0),
    ("org_acme", "revenue", "2026-06-05", 1_300_000.0),
    ("org_acme", "revenue", "2026-06-06", 2_220_000.0),
    ("org_acme", "revenue", "2026-06-07", 1_260_000.0),
    ("org_acme", "revenue", "2026-06-08", 1_130_000.0),
    ("org_acme", "revenue", "2026-06-09", 1_170_000.0),
    ("org_acme", "revenue", "2026-06-10", 1_020_000.0),
    ("org_acme", "conversion", "2026-05-12", 9.4),
    ("org_acme", "conversion", "2026-05-13", 10.6),
    ("org_acme", "conversion", "2026-05-14", 9.8),
    ("org_acme", "conversion", "2026-05-15", 7.1),
    ("org_acme", "conversion", "2026-05-16", 9.3),
    ("org_acme", "conversion", "2026-05-17", 7.2),
    ("org_acme", "conversion", "2026-05-18", 7.4),
    ("org_acme", "conversion", "2026-05-19", 12.4),
    ("org_acme", "conversion", "2026-05-20", 9.6),
    ("org_acme", "conversion", "2026-05-21", 9.0),
    ("org_acme", "conversion", "2026-05-22", 10.2),
    ("org_acme", "conversion", "2026-05-23", 9.1),
    ("org_acme", "conversion", "2026-05-24", 10.8),
    ("org_acme", "conversion", "2026-05-25", 10.2),
    ("org_acme", "conversion", "2026-05-26", 7.5),
    ("org_acme", "conversion", "2026-05-27", 12.4),
    ("org_acme", "conversion", "2026-05-28", 13.0),
    ("org_acme", "conversion", "2026-05-29", 13.5),
    ("org_acme", "conversion", "2026-05-30", 9.7),
    ("org_acme", "conversion", "2026-05-31", 10.0),
    ("org_acme", "conversion", "2026-06-01", 7.2),
    ("org_acme", "conversion", "2026-06-02", 6.5),
    ("org_acme", "conversion", "2026-06-03", 14.2),
    ("org_acme", "conversion", "2026-06-04", 13.1),
    ("org_acme", "conversion", "2026-06-05", 21.0),
    ("org_acme", "conversion", "2026-06-06", 13.0),
    ("org_acme", "conversion", "2026-06-07", 9.7),
    ("org_acme", "conversion", "2026-06-08", 11.0),
    ("org_acme", "conversion", "2026-06-09", 9.9),
    ("org_acme", "conversion", "2026-06-10", 12.1),
]

CODEX_THREADS = [
    {
        "id": "thread_checkout_conversion",
        "title": "Explain checkout conversion",
        "status": "complete",
        "turns": [
            {
                "id": "turn_checkout_user",
                "role": "user",
                "markdown": "Explain checkout conversion for the current funnel dashboard.",
                "created_at": "2026-05-17T20:45:00Z",
            },
            {
                "id": "turn_checkout_assistant",
                "role": "assistant",
                "markdown": (
                    "### Checkout conversion read\n\n"
                    "Conversion is healthy overall, but the `Payment Info Entered` step is the main compression point. "
                    "The current funnel implies a **12.4% session-to-purchase rate**.\n\n"
                    "```mermaid\n"
                    "flowchart LR\n"
                    "  Sessions[Sessions] --> Cart[Added to Cart]\n"
                    "  Cart --> Checkout[Reached Checkout]\n"
                    "  Checkout --> Payment[Payment Info Entered]\n"
                    "  Payment --> Purchase[Purchase Completed]\n"
                    "```\n\n"
                    "The Mermaid block is intentionally rendered as a diagram-ready placeholder in this slice."
                ),
                "created_at": "2026-05-17T20:45:12Z",
            },
        ],
    },
    {
        "id": "thread_experiment_rollout",
        "title": "Create experiment rollout dashboard",
        "status": "complete",
        "turns": [
            {
                "id": "turn_experiment_user",
                "role": "user",
                "markdown": "Build a dashboard to track rollout and impact of a new pricing experiment.",
                "created_at": "2026-05-17T20:50:00Z",
            },
            {
                "id": "turn_experiment_assistant",
                "role": "assistant",
                "markdown": (
                    "### Proposed rollout dashboard\n\n"
                    "- Exposure by platform and country\n"
                    "- Checkout conversion split by variant\n"
                    "- Revenue per visitor and refund rate\n\n"
                    "Start with a personal dashboard, then promote it if the experiment readout becomes recurring."
                ),
                "created_at": "2026-05-17T20:50:09Z",
            },
        ],
    },
    {
        "id": "thread_android_dip",
        "title": "Investigate Android dip",
        "status": "running",
        "turns": [
            {
                "id": "turn_android_user",
                "role": "user",
                "markdown": "Android conversion rate dropped around Jun 2. What happened?",
                "created_at": "2026-05-17T20:55:00Z",
            },
            {
                "id": "turn_android_assistant",
                "role": "assistant",
                "markdown": "Codex is comparing Android checkout events against payment error logs and campaign mix.",
                "created_at": "2026-05-17T20:55:10Z",
            },
        ],
    },
    {
        "id": "thread_revenue_week",
        "title": "What's driving revenue this week?",
        "status": "queued",
        "turns": [],
    },
]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_databases(app_db_path: Path, metrics_db_path: Path, demo_mode: bool) -> None:
    with connect(app_db_path) as app_db:
        app_db.execute("PRAGMA foreign_keys = ON")
        app_db.execute(
            """
            CREATE TABLE IF NOT EXISTS orgs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        app_db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL REFERENCES orgs(id),
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'analyst', 'viewer')),
                password_hash TEXT NOT NULL
            )
            """
        )
        app_db.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboards (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL REFERENCES orgs(id),
                owner_user_id TEXT REFERENCES users(id),
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                space TEXT NOT NULL CHECK (space IN ('org', 'personal')),
                description TEXT NOT NULL,
                UNIQUE(org_id, slug)
            )
            """
        )
        if demo_mode:
            seed_demo_app_state(app_db)

    with connect(metrics_db_path) as metrics_db:
        metrics_db.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                observed_on TEXT NOT NULL,
                value REAL NOT NULL,
                UNIQUE(org_id, metric, observed_on)
            )
            """
        )
        metrics_db.executemany(
            """
            INSERT INTO metric_points (org_id, metric, observed_on, value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(org_id, metric, observed_on) DO UPDATE SET
                value = excluded.value
            """,
            METRIC_SERIES,
        )


def seed_demo_app_state(app_db: sqlite3.Connection) -> None:
    app_db.execute(
        """
        INSERT INTO orgs (id, name)
        VALUES (:id, :name)
        ON CONFLICT(id) DO UPDATE SET name = excluded.name
        """,
        DEMO_ORG,
    )
    app_db.executemany(
        """
        INSERT INTO users (id, org_id, email, name, role, password_hash)
        VALUES (:id, :org_id, :email, :name, :role, :password_hash)
        ON CONFLICT(email) DO UPDATE SET
            org_id = excluded.org_id,
            name = excluded.name,
            role = excluded.role
        """,
        [
            {
                "id": user["id"],
                "org_id": user["org_id"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "password_hash": hash_password(user["password"]),
            }
            for user in DEMO_USERS
        ],
    )
    app_db.executemany(
        """
        INSERT INTO dashboards (id, org_id, owner_user_id, slug, name, space, description)
        VALUES (:id, :org_id, NULL, :slug, :name, 'org', :description)
        ON CONFLICT(org_id, slug) DO UPDATE SET
            owner_user_id = excluded.owner_user_id,
            name = excluded.name,
            space = excluded.space,
            description = excluded.description
        """,
        [{**dashboard, "org_id": DEMO_ORG["id"]} for dashboard in ORG_DASHBOARDS],
    )
    app_db.executemany(
        """
        INSERT INTO dashboards (id, org_id, owner_user_id, slug, name, space, description)
        VALUES (:id, :org_id, :owner_user_id, :slug, :name, 'personal', :description)
        ON CONFLICT(org_id, slug) DO UPDATE SET
            owner_user_id = excluded.owner_user_id,
            name = excluded.name,
            space = excluded.space,
            description = excluded.description
        """,
        [{**dashboard, "org_id": DEMO_ORG["id"]} for dashboard in PERSONAL_DASHBOARDS],
    )


def get_user_by_email(app_db_path: Path, email: str) -> User | None:
    with connect(app_db_path) as app_db:
        row = app_db.execute(
            """
            SELECT id, email, name, org_id, role, password_hash
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()
    return User(**dict(row)) if row else None


def list_dashboards(
    app_db_path: Path,
    *,
    org_id: str,
    space: str | None = None,
    owner_user_id: str | None = None,
) -> list[dict[str, str | int | None]]:
    filters = ["org_id = ?"]
    params: list[str] = [org_id]
    if space:
        filters.append("space = ?")
        params.append(space)
    if owner_user_id:
        filters.append("owner_user_id = ?")
        params.append(owner_user_id)

    with connect(app_db_path) as app_db:
        rows = app_db.execute(
            f"""
            SELECT id, org_id, owner_user_id, slug, name, space, description
            FROM dashboards
            WHERE {" AND ".join(filters)}
            ORDER BY
                CASE slug
                    WHEN 'revenue-overview' THEN 1
                    WHEN 'checkout-funnel' THEN 2
                    WHEN 'campaign-performance' THEN 3
                    ELSE 100
                END,
                name
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_dashboard_summary(
    app_db_path: Path,
    *,
    dashboard_id: str,
    org_id: str,
    user_id: str,
) -> dict[str, str | int | None] | None:
    with connect(app_db_path) as app_db:
        row = app_db.execute(
            """
            SELECT id, org_id, owner_user_id, slug, name, space, description
            FROM dashboards
            WHERE id = ?
                AND org_id = ?
                AND (space = 'org' OR owner_user_id = ?)
            """,
            (dashboard_id, org_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def list_metric_points(
    metrics_db_path: Path,
    *,
    org_id: str,
    metric: str,
) -> list[dict[str, str | float]]:
    with connect(metrics_db_path) as metrics_db:
        rows = metrics_db.execute(
            """
            SELECT metric, observed_on, value
            FROM metric_points
            WHERE org_id = ? AND metric = ?
            ORDER BY observed_on
            """,
            (org_id, metric),
        ).fetchall()
    return [dict(row) for row in rows]


def get_dashboard_detail(
    app_db_path: Path,
    metrics_db_path: Path,
    *,
    dashboard_id: str,
    org_id: str,
    user_id: str,
) -> dict[str, object] | None:
    summary = get_dashboard_summary(
        app_db_path,
        dashboard_id=dashboard_id,
        org_id=org_id,
        user_id=user_id,
    )
    if not summary:
        return None

    revenue = list_metric_points(metrics_db_path, org_id=org_id, metric="revenue")
    conversion = list_metric_points(metrics_db_path, org_id=org_id, metric="conversion")
    panels = panels_for_dashboard(str(summary["slug"]), revenue, conversion)
    return {
        **summary,
        "time_range_label": "May 12 - Jun 10, 2026",
        "panels": panels,
    }


def panels_for_dashboard(
    slug: str,
    revenue: list[dict[str, str | float]],
    conversion: list[dict[str, str | float]],
) -> list[dict[str, object]]:
    if slug == "checkout-funnel":
        return [
            {
                "id": "panel_revenue_over_time",
                "title": "Revenue Over Time",
                "type": "line",
                "metric_key": "revenue",
                "value_format": "currency",
                "data": revenue,
            },
            {
                "id": "panel_conversion_over_time",
                "title": "Checkout Conversion Over Time",
                "type": "line",
                "metric_key": "conversion",
                "value_format": "percent",
                "data": conversion,
            },
            {
                "id": "panel_platform_conversion",
                "title": "Conversion Rate by Platform",
                "type": "bar",
                "metric_key": "conversion_by_platform",
                "value_format": "percent",
                "data": [
                    {"label": "Web", "value": 14.6},
                    {"label": "iOS", "value": 16.8},
                    {"label": "Android", "value": 9.7},
                ],
            },
            {
                "id": "panel_checkout_funnel",
                "title": "Checkout Funnel",
                "type": "funnel",
                "metric_key": "checkout_funnel",
                "value_format": "integer",
                "data": [
                    {"label": "Sessions", "value": 482_128, "rate": None},
                    {"label": "Added to Cart", "value": 191_889, "rate": 39.8},
                    {"label": "Reached Checkout", "value": 93_215, "rate": 19.3},
                    {"label": "Payment Info Entered", "value": 64_017, "rate": 13.3},
                    {"label": "Purchase Completed", "value": 59_821, "rate": 12.4},
                ],
            },
        ]
    if slug == "campaign-performance":
        return [
            {
                "id": "panel_campaign_revenue",
                "title": "Campaign Revenue Over Time",
                "type": "line",
                "metric_key": "revenue",
                "value_format": "currency",
                "data": revenue,
            },
            {
                "id": "panel_channel_conversion",
                "title": "Conversion Rate by Channel",
                "type": "bar",
                "metric_key": "conversion_by_channel",
                "value_format": "percent",
                "data": [
                    {"label": "Search", "value": 15.2},
                    {"label": "Paid Social", "value": 11.4},
                    {"label": "Email", "value": 18.1},
                ],
            },
        ]
    return [
        {
            "id": "panel_revenue_over_time",
            "title": "Revenue Over Time",
            "type": "line",
            "metric_key": "revenue",
            "value_format": "currency",
            "data": revenue,
        },
        {
            "id": "panel_conversion_over_time",
            "title": "Conversion Over Time",
            "type": "line",
            "metric_key": "conversion",
            "value_format": "percent",
            "data": conversion,
        },
    ]


def list_codex_threads() -> list[dict[str, object]]:
    return CODEX_THREADS


def database_paths_exist(*paths: Path) -> Iterator[tuple[str, bool]]:
    for path in paths:
        yield str(path), path.exists()
