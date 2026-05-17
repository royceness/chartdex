import sqlite3
from collections.abc import Iterator
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys

from app.auth import User, hash_password
from app.metrics_provider import SQLiteMetricsProvider, get_metrics_provider_for_org

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
    if demo_mode:
        ensure_demo_metrics_database(metrics_db_path)

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
        app_db.execute(
            """
            CREATE TABLE IF NOT EXISTS org_metric_providers (
                org_id TEXT PRIMARY KEY REFERENCES orgs(id),
                provider_type TEXT NOT NULL,
                config_json TEXT NOT NULL
            )
            """
        )
        if demo_mode:
            seed_demo_app_state(app_db, metrics_db_path)


def ensure_demo_metrics_database(metrics_db_path: Path) -> None:
    if metrics_db_path.exists() and metrics_database_has_required_schema(metrics_db_path):
        return

    generator_path = Path(__file__).resolve().parents[2] / "scripts" / "generate_demo_metrics.py"
    spec = importlib.util.spec_from_file_location("generate_demo_metrics", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load demo metrics generator from {generator_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.generate_database(
        metrics_db_path,
        days=180,
        seed=42,
        end_date=date(2026, 5, 18),
    )


def metrics_database_has_required_schema(metrics_db_path: Path) -> bool:
    with sqlite3.connect(metrics_db_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('metric_facts_daily', 'seed_dashboards', 'metric_catalog')
            """
        ).fetchone()
    return bool(row and row[0] == 3)


def seed_demo_app_state(app_db: sqlite3.Connection, metrics_db_path: Path) -> None:
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
    app_db.execute(
        """
        INSERT INTO org_metric_providers (org_id, provider_type, config_json)
        VALUES (?, 'sqlite', ?)
        ON CONFLICT(org_id) DO UPDATE SET
            provider_type = excluded.provider_type,
            config_json = excluded.config_json
        """,
        (DEMO_ORG["id"], json.dumps({"db_path": str(metrics_db_path)})),
    )
    seed_dashboards = SQLiteMetricsProvider(metrics_db_path).list_seed_dashboards()
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
        [
            {
                "id": dashboard["id"],
                "org_id": DEMO_ORG["id"],
                "slug": dashboard_slug(str(dashboard["id"])),
                "name": dashboard["title"],
                "description": dashboard["description"],
            }
            for dashboard in seed_dashboards
        ],
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


def dashboard_slug(dashboard_id: str) -> str:
    return dashboard_id.removeprefix("dash_").replace("_", "-")


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
    app_db_path: Path,
    *,
    org_id: str,
    metric: str,
) -> list[dict[str, object]]:
    provider = get_metrics_provider_for_org(app_db_path, org_id)
    return provider.list_metric_points(metric)


def get_dashboard_detail(
    app_db_path: Path,
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

    provider = get_metrics_provider_for_org(app_db_path, org_id)
    return provider.get_dashboard_detail(summary)


def list_codex_threads() -> list[dict[str, object]]:
    return CODEX_THREADS


def database_paths_exist(*paths: Path) -> Iterator[tuple[str, bool]]:
    for path in paths:
        yield str(path), path.exists()
