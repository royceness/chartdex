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
    ("org_acme", "revenue", "2026-05-11", 128400.0),
    ("org_acme", "revenue", "2026-05-12", 131900.0),
    ("org_acme", "revenue", "2026-05-13", 126100.0),
    ("org_acme", "revenue", "2026-05-14", 139250.0),
    ("org_acme", "revenue", "2026-05-15", 142800.0),
    ("org_acme", "conversion", "2026-05-11", 3.42),
    ("org_acme", "conversion", "2026-05-12", 3.38),
    ("org_acme", "conversion", "2026-05-13", 3.21),
    ("org_acme", "conversion", "2026-05-14", 3.48),
    ("org_acme", "conversion", "2026-05-15", 3.55),
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


def database_paths_exist(*paths: Path) -> Iterator[tuple[str, bool]]:
    for path in paths:
        yield str(path), path.exists()
