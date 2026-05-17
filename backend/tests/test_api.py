from collections.abc import Iterator
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.auth import verify_password
from app.main import app
from app.settings import get_settings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CHARTDEX_APP_DB_PATH", str(tmp_path / "app_state.sqlite3"))
    monkeypatch.setenv("CHARTDEX_METRICS_DB_PATH", str(tmp_path / "metrics.sqlite3"))
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_health_initializes_separate_databases(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["databases"]) == 2
    assert all(payload["databases"].values())


def test_lists_seeded_org_dashboards(client: TestClient) -> None:
    login(client)

    response = client.get("/api/dashboards")

    assert response.status_code == 200
    dashboards = response.json()["dashboards"]
    assert [dashboard["name"] for dashboard in dashboards] == [
        "Revenue Overview",
        "Checkout Funnel",
        "Campaign Performance",
    ]
    assert {dashboard["space"] for dashboard in dashboards} == {"org"}
    assert {dashboard["org_id"] for dashboard in dashboards} == {"org_acme"}


def test_lists_seeded_metric_points(client: TestClient) -> None:
    login(client)

    response = client.get("/api/metrics/revenue")

    assert response.status_code == 200
    points = response.json()["points"]
    assert points[0] == {"metric": "revenue", "observed_on": "2026-05-11", "value": 128400.0}
    assert len(points) == 5


def test_login_sets_cookie_and_me_reads_auth_context(client: TestClient) -> None:
    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"] == {
        "user_id": "u_admin",
        "email": "admin@acme.test",
        "name": "Avery Admin",
        "org_id": "org_acme",
        "role": "admin",
    }
    assert "chartdex_access_token" in response.cookies

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "admin@acme.test"


def test_analyst_login_works(client: TestClient) -> None:
    response = login(client, email="analyst@acme.test")

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "analyst"


def test_invalid_login_fails(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@acme.test", "password": "wrong"},
    )

    assert response.status_code == 401
    assert "chartdex_access_token" not in response.cookies


def test_protected_routes_require_cookie(client: TestClient) -> None:
    dashboards_response = client.get("/api/dashboards")
    metrics_response = client.get("/api/metrics/revenue")

    assert dashboards_response.status_code == 401
    assert metrics_response.status_code == 401


def test_logout_clears_cookie_and_session(client: TestClient) -> None:
    login(client)

    logout_response = client.post("/api/auth/logout")
    me_response = client.get("/api/auth/me")

    assert logout_response.status_code == 200
    assert me_response.status_code == 401


def test_seeded_passwords_are_hashed(tmp_path: Path, client: TestClient) -> None:
    app_db_path = tmp_path / "app_state.sqlite3"
    with sqlite3.connect(app_db_path) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("admin@acme.test",),
        ).fetchone()

    assert row is not None
    assert row[0] != "password"
    assert verify_password("password", row[0])


def login(
    client: TestClient,
    *,
    email: str = "admin@acme.test",
    password: str = "password",
):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
