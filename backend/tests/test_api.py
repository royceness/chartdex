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


def test_lists_seeded_dashboards(client: TestClient) -> None:
    login(client)

    response = client.get("/api/dashboards")

    assert response.status_code == 200
    dashboards = response.json()["dashboards"]
    assert {"Revenue Overview", "Checkout Funnel", "Campaign Performance"}.issubset(
        {dashboard["name"] for dashboard in dashboards}
    )
    assert {"org", "personal"} == {dashboard["space"] for dashboard in dashboards}
    assert {dashboard["org_id"] for dashboard in dashboards} == {"org_acme"}
    assert {"Growth Experiments", "A/B Test Results"}.issubset(
        {dashboard["name"] for dashboard in dashboards}
    )


def test_personal_dashboards_are_scoped_to_user(client: TestClient) -> None:
    login(client, email="analyst@acme.test")

    response = client.get("/api/dashboards")

    assert response.status_code == 200
    dashboards = response.json()["dashboards"]
    personal_names = {dashboard["name"] for dashboard in dashboards if dashboard["space"] == "personal"}
    assert personal_names == {"Data Quality"}


def test_lists_seeded_metric_points(client: TestClient) -> None:
    login(client)

    response = client.get("/api/metrics/revenue")

    assert response.status_code == 200
    points = response.json()["points"]
    assert points[0]["metric"] == "revenue"
    assert points[0]["observed_on"] == "2026-04-19"
    assert points[0]["value"] > 100_000
    assert len(points) == 30


def test_gets_dashboard_detail_with_panels(client: TestClient) -> None:
    login(client)

    response = client.get("/api/dashboards/dash_checkout_funnel")

    assert response.status_code == 200
    dashboard = response.json()["dashboard"]
    assert dashboard["name"] == "Checkout Funnel"
    assert [panel["type"] for panel in dashboard["panels"]] == ["funnel", "line", "bar", "bar"]
    assert dashboard["panels"][1]["data"][0]["observed_on"] == "2026-04-19"
    assert dashboard["panels"][1]["metric_key"] == "checkout_conversion"


def test_lists_persisted_codex_threads(client: TestClient) -> None:
    login(client)

    response = client.get("/api/codex/threads")

    assert response.status_code == 200
    threads = response.json()["threads"]
    titles = {thread["title"] for thread in threads}
    assert "Explain checkout conversion" in titles
    checkout_thread = next(thread for thread in threads if thread["title"] == "Explain checkout conversion")
    assert "```mermaid" in checkout_thread["turns"][1]["markdown"]
    assert checkout_thread["context"]["dashboard_id"] == "dash_checkout_funnel"


def test_creates_codex_thread_with_validated_context(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/codex/threads",
        json={
            "title": "Investigate Android checkout dip",
            "utterance": "Android conversion dropped around Jun 2. What happened?",
            "context": {
                "dashboard_id": "dash_checkout_funnel",
                "panel_id": "panel_checkout_conversion",
                "metric_key": "checkout_conversion",
                "range_start": "2026-06-01",
                "range_end": "2026-06-07",
            },
        },
    )

    assert response.status_code == 201
    created_thread = response.json()["thread"]
    assert created_thread["status"] == "queued"
    assert created_thread["turns"][0]["role"] == "user"
    assert created_thread["context"]["panel_id"] == "panel_checkout_conversion"

    detail_response = client.get(f"/api/codex/threads/{created_thread['id']}")

    assert detail_response.status_code == 200
    completed_thread = detail_response.json()["thread"]
    assert completed_thread["status"] == "complete"
    assert completed_thread["turns"][-1]["role"] == "assistant"
    assert "external Codex app-server provider can replace this executor" in completed_thread["turns"][-1]["markdown"]


def test_codex_thread_context_rejects_panel_from_wrong_dashboard(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/codex/threads",
        json={
            "title": "Bad context",
            "utterance": "Use a mismatched panel.",
            "context": {
                "dashboard_id": "dash_checkout_funnel",
                "panel_id": "panel_revenue_over_time",
                "metric_key": "revenue",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Panel does not belong to dashboard"


def test_codex_threads_are_scoped_to_owner(client: TestClient) -> None:
    login(client)
    create_response = client.post(
        "/api/codex/threads",
        json={"title": "Admin-only thread", "utterance": "Keep this in my workspace."},
    )
    thread_id = create_response.json()["thread"]["id"]
    client.post("/api/auth/logout")
    login(client, email="analyst@acme.test")

    detail_response = client.get(f"/api/codex/threads/{thread_id}")

    assert detail_response.status_code == 404


def test_follow_up_rejects_running_thread(tmp_path: Path, client: TestClient) -> None:
    login(client)
    app_db_path = tmp_path / "app_state.sqlite3"
    with sqlite3.connect(app_db_path) as connection:
        connection.execute(
            """
            INSERT INTO codex_threads (
                id, org_id, owner_user_id, title, status, context_json, created_at, updated_at
            )
            VALUES (
                'thread_busy_test', 'org_acme', 'u_admin', 'Busy thread', 'running',
                NULL, '2026-05-17T21:10:00Z', '2026-05-17T21:10:00Z'
            )
            """
        )

    response = client.post(
        "/api/codex/threads/thread_busy_test/turns",
        json={"utterance": "Can you continue?"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Codex thread is still running"


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
    dashboard_detail_response = client.get("/api/dashboards/dash_checkout_funnel")
    threads_response = client.get("/api/codex/threads")
    create_thread_response = client.post(
        "/api/codex/threads",
        json={"title": "No auth", "utterance": "Should fail"},
    )
    metrics_response = client.get("/api/metrics/revenue")

    assert dashboards_response.status_code == 401
    assert dashboard_detail_response.status_code == 401
    assert threads_response.status_code == 401
    assert create_thread_response.status_code == 401
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
