import sqlite3
from collections.abc import Iterator
from pathlib import Path


ORG_DASHBOARDS = [
    {
        "slug": "revenue-overview",
        "name": "Revenue Overview",
        "description": "Revenue, orders, and average order value across the store.",
    },
    {
        "slug": "checkout-funnel",
        "name": "Checkout Funnel",
        "description": "Session-to-purchase conversion and step drop-off.",
    },
    {
        "slug": "campaign-performance",
        "name": "Campaign Performance",
        "description": "Paid campaign spend, revenue, and return on ad spend.",
    },
]

METRIC_SERIES = [
    ("revenue", "2026-05-11", 128400.0),
    ("revenue", "2026-05-12", 131900.0),
    ("revenue", "2026-05-13", 126100.0),
    ("revenue", "2026-05-14", 139250.0),
    ("revenue", "2026-05-15", 142800.0),
    ("conversion", "2026-05-11", 3.42),
    ("conversion", "2026-05-12", 3.38),
    ("conversion", "2026-05-13", 3.21),
    ("conversion", "2026-05-14", 3.48),
    ("conversion", "2026-05-15", 3.55),
]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_databases(app_db_path: Path, metrics_db_path: Path) -> None:
    with connect(app_db_path) as app_db:
        app_db.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                space TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        app_db.executemany(
            """
            INSERT INTO dashboards (slug, name, space, description)
            VALUES (:slug, :name, 'org', :description)
            ON CONFLICT(slug) DO UPDATE SET
                name = excluded.name,
                space = excluded.space,
                description = excluded.description
            """,
            ORG_DASHBOARDS,
        )

    with connect(metrics_db_path) as metrics_db:
        metrics_db.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric TEXT NOT NULL,
                observed_on TEXT NOT NULL,
                value REAL NOT NULL,
                UNIQUE(metric, observed_on)
            )
            """
        )
        metrics_db.executemany(
            """
            INSERT INTO metric_points (metric, observed_on, value)
            VALUES (?, ?, ?)
            ON CONFLICT(metric, observed_on) DO UPDATE SET
                value = excluded.value
            """,
            METRIC_SERIES,
        )


def list_dashboards(app_db_path: Path) -> list[dict[str, str | int]]:
    with connect(app_db_path) as app_db:
        rows = app_db.execute(
            """
            SELECT id, slug, name, space, description
            FROM dashboards
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_metric_points(metrics_db_path: Path, metric: str) -> list[dict[str, str | float]]:
    with connect(metrics_db_path) as metrics_db:
        rows = metrics_db.execute(
            """
            SELECT metric, observed_on, value
            FROM metric_points
            WHERE metric = ?
            ORDER BY observed_on
            """,
            (metric,),
        ).fetchall()
    return [dict(row) for row in rows]


def database_paths_exist(*paths: Path) -> Iterator[tuple[str, bool]]:
    for path in paths:
        yield str(path), path.exists()
