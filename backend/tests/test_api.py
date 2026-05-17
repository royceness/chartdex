from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    response = client.get("/api/dashboards")

    assert response.status_code == 200
    dashboards = response.json()["dashboards"]
    assert [dashboard["name"] for dashboard in dashboards] == [
        "Revenue Overview",
        "Checkout Funnel",
        "Campaign Performance",
    ]
    assert {dashboard["space"] for dashboard in dashboards} == {"org"}


def test_lists_seeded_metric_points(client: TestClient) -> None:
    response = client.get("/api/metrics/revenue")

    assert response.status_code == 200
    points = response.json()["points"]
    assert points[0] == {"metric": "revenue", "observed_on": "2026-05-11", "value": 128400.0}
    assert len(points) == 5
