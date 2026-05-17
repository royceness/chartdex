from collections.abc import Iterator
from pathlib import Path

import anyio
from fastapi.testclient import TestClient
import pytest

from app.codex_tools import ChartDexToolContext, dynamic_tool_specs, handle_tool_call
from app.github_tools import GitHubRepository
from app.main import app
from app.settings import get_settings


@pytest.fixture
def initialized_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    app_db_path = tmp_path / "app_state.sqlite3"
    monkeypatch.setenv("CHARTDEX_APP_DB_PATH", str(app_db_path))
    monkeypatch.setenv("CHARTDEX_METRICS_DB_PATH", str(tmp_path / "metrics.sqlite3"))
    monkeypatch.setenv("CHARTDEX_GITHUB_REPOSITORY", "royceness/acme-outdoor-demo-store")
    get_settings.cache_clear()
    with TestClient(app):
        yield app_db_path
    get_settings.cache_clear()


def test_dynamic_tool_specs_include_github_namespace() -> None:
    github_tools = [tool for tool in dynamic_tool_specs() if tool["namespace"] == "github"]

    assert {tool["name"] for tool in github_tools} == {
        "get_repository",
        "search_commits",
        "search_code",
        "get_commit",
        "get_pull_request",
    }
    assert all("repo" not in tool["inputSchema"].get("properties", {}) for tool in github_tools)


def test_github_search_commits_uses_single_org_configured_repository(
    initialized_app: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeGitHubClient()
    monkeypatch.setattr("app.github_tools.github_client", fake_client)
    context = ChartDexToolContext(
        app_db_path=initialized_app,
        org_id="org_acme",
        user_id="u_admin",
        thread_id="thread_test",
    )

    result = anyio.run(
        handle_tool_call,
        context,
        "github",
        "search_commits",
        {"query": "promo android", "since": "2026-05-01", "until": "2026-05-18", "limit": 50},
    )

    assert "promo fix" in result
    assert fake_client.commit_searches == [
        {
            "repo": GitHubRepository(owner="royceness", name="acme-outdoor-demo-store"),
            "query": "promo android",
            "since": "2026-05-01",
            "until": "2026-05-18",
            "path": None,
            "limit": 20,
        }
    ]


def test_github_tools_reject_model_supplied_repository_argument(
    initialized_app: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.github_tools.github_client", FakeGitHubClient())
    context = ChartDexToolContext(
        app_db_path=initialized_app,
        org_id="org_acme",
        user_id="u_admin",
        thread_id="thread_test",
    )

    with pytest.raises(ValueError, match="Unsupported GitHub tool arguments: repo"):
        anyio.run(
            handle_tool_call,
            context,
            "github",
            "search_commits",
            {"query": "promo android", "repo": "evil/other"},
        )


class FakeGitHubClient:
    def __init__(self) -> None:
        self.commit_searches: list[dict[str, object]] = []

    def repository(self, repo: GitHubRepository) -> dict[str, object]:
        return {
            "full_name": repo.full_name,
            "private": True,
            "default_branch": "main",
            "html_url": f"https://github.com/{repo.full_name}",
            "description": "Demo repo",
        }

    def search_commits(
        self,
        repo: GitHubRepository,
        *,
        query: str,
        since: str | None,
        until: str | None,
        path: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        self.commit_searches.append(
            {
                "repo": repo,
                "query": query,
                "since": since,
                "until": until,
                "path": path,
                "limit": limit,
            }
        )
        return [
            {
                "sha": "abc123",
                "html_url": f"https://github.com/{repo.full_name}/commit/abc123",
                "message": "promo fix",
                "author_name": "Avery Admin",
                "author_date": "2026-05-10T12:00:00Z",
                "committer_date": "2026-05-10T12:00:00Z",
            }
        ]

    def search_code(
        self,
        repo: GitHubRepository,
        *,
        query: str,
        path: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        return []

    def get_commit(self, repo: GitHubRepository, *, sha: str) -> dict[str, object]:
        return {"sha": sha}

    def get_pull_request(self, repo: GitHubRepository, *, number: int) -> dict[str, object]:
        return {"number": number}
