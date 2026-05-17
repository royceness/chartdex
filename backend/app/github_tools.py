from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.database import get_github_repository_for_org
from app.settings import get_settings

if TYPE_CHECKING:
    from app.codex_tools import ChartDexToolContext


GITHUB_NAMESPACE = "github"
MAX_GITHUB_TEXT_CHARS = 40_000
MAX_BODY_CHARS = 4_000
MAX_PATCH_CHARS = 2_000
DEFAULT_LIMIT = 10
MAX_LIMIT = 20


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubClient(Protocol):
    def repository(self, repo: GitHubRepository) -> dict[str, object]:
        ...

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
        ...

    def search_code(
        self,
        repo: GitHubRepository,
        *,
        query: str,
        path: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        ...

    def get_commit(self, repo: GitHubRepository, *, sha: str) -> dict[str, object]:
        ...

    def get_pull_request(self, repo: GitHubRepository, *, number: int) -> dict[str, object]:
        ...


class UrlLibGitHubClient:
    api_base = "https://api.github.com"

    def repository(self, repo: GitHubRepository) -> dict[str, object]:
        payload = self._request_json(f"/repos/{repo.owner}/{repo.name}")
        return {
            "full_name": payload["full_name"],
            "private": payload["private"],
            "default_branch": payload["default_branch"],
            "html_url": payload["html_url"],
            "description": payload.get("description"),
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
        search_terms = [query, f"repo:{repo.full_name}"]
        if since:
            search_terms.append(f"committer-date:>={since}")
        if until:
            search_terms.append(f"committer-date:<={until}")
        if path:
            search_terms.append(f"path:{path}")
        payload = self._request_json(
            "/search/commits",
            {
                "q": " ".join(search_terms),
                "per_page": str(limit),
            },
        )
        return [
            {
                "sha": item["sha"],
                "html_url": item["html_url"],
                "message": first_line(item["commit"]["message"]),
                "author_name": (item["commit"].get("author") or {}).get("name"),
                "author_date": (item["commit"].get("author") or {}).get("date"),
                "committer_date": (item["commit"].get("committer") or {}).get("date"),
            }
            for item in payload.get("items", [])[:limit]
        ]

    def search_code(
        self,
        repo: GitHubRepository,
        *,
        query: str,
        path: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        search_terms = [query, f"repo:{repo.full_name}"]
        if path:
            search_terms.append(f"path:{path}")
        payload = self._request_json(
            "/search/code",
            {
                "q": " ".join(search_terms),
                "per_page": str(limit),
            },
        )
        return [
            {
                "name": item["name"],
                "path": item["path"],
                "sha": item["sha"],
                "html_url": item["html_url"],
                "repository": item["repository"]["full_name"],
            }
            for item in payload.get("items", [])[:limit]
        ]

    def get_commit(self, repo: GitHubRepository, *, sha: str) -> dict[str, object]:
        payload = self._request_json(f"/repos/{repo.owner}/{repo.name}/commits/{sha}")
        files = payload.get("files", [])
        return {
            "sha": payload["sha"],
            "html_url": payload["html_url"],
            "message": payload["commit"]["message"],
            "author": payload["commit"].get("author"),
            "committer": payload["commit"].get("committer"),
            "stats": payload.get("stats"),
            "files": [
                {
                    "filename": item["filename"],
                    "status": item["status"],
                    "additions": item.get("additions"),
                    "deletions": item.get("deletions"),
                    "changes": item.get("changes"),
                    "patch": truncate_text(item.get("patch"), MAX_PATCH_CHARS),
                }
                for item in files[:10]
            ],
            "file_count": len(files),
        }

    def get_pull_request(self, repo: GitHubRepository, *, number: int) -> dict[str, object]:
        pull = self._request_json(f"/repos/{repo.owner}/{repo.name}/pulls/{number}")
        files_payload = self._request_json(
            f"/repos/{repo.owner}/{repo.name}/pulls/{number}/files",
            {"per_page": "30"},
        )
        return {
            "number": pull["number"],
            "title": pull["title"],
            "state": pull["state"],
            "html_url": pull["html_url"],
            "user": (pull.get("user") or {}).get("login"),
            "created_at": pull["created_at"],
            "merged_at": pull.get("merged_at"),
            "base_ref": pull["base"]["ref"],
            "head_ref": pull["head"]["ref"],
            "body": truncate_text(pull.get("body"), MAX_BODY_CHARS),
            "files": [
                {
                    "filename": item["filename"],
                    "status": item["status"],
                    "additions": item.get("additions"),
                    "deletions": item.get("deletions"),
                    "changes": item.get("changes"),
                    "patch": truncate_text(item.get("patch"), MAX_PATCH_CHARS),
                }
                for item in files_payload[:30]
            ],
            "changed_files": pull.get("changed_files"),
        }

    def _request_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self.api_base}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "chartdex-codex-tools",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = get_settings().github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode())
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"GitHub API request failed: HTTP {exc.code} {body}") from exc


github_client: GitHubClient = UrlLibGitHubClient()


def github_tool_specs() -> list[dict[str, object]]:
    return [
        {
            "namespace": GITHUB_NAMESPACE,
            "name": "get_repository",
            "description": "Return the single GitHub repository configured for this ChartDex organization.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            "exposeToContext": True,
        },
        {
            "namespace": GITHUB_NAMESPACE,
            "name": "search_commits",
            "description": "Search commits in the configured repository. The repository is fixed by the backend.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "since": {"type": "string"},
                    "until": {"type": "string"},
                    "path": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                },
            },
            "exposeToContext": True,
        },
        {
            "namespace": GITHUB_NAMESPACE,
            "name": "search_code",
            "description": "Search code in the configured repository. The repository is fixed by the backend.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                },
            },
            "exposeToContext": True,
        },
        {
            "namespace": GITHUB_NAMESPACE,
            "name": "get_commit",
            "description": "Fetch one commit from the configured repository with bounded file patches.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sha"],
                "properties": {"sha": {"type": "string"}},
            },
            "exposeToContext": True,
        },
        {
            "namespace": GITHUB_NAMESPACE,
            "name": "get_pull_request",
            "description": "Fetch one pull request from the configured repository with bounded changed files.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["number"],
                "properties": {"number": {"type": "integer", "minimum": 1}},
            },
            "exposeToContext": True,
        },
    ]


async def handle_github_tool_call(context: "ChartDexToolContext", tool: str, arguments: Any) -> str:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    repo = configured_repository(context)
    if tool == "get_repository":
        ensure_allowed_arguments(arguments, set())
        return github_json({"repository": github_client.repository(repo)})
    if tool == "search_commits":
        ensure_allowed_arguments(arguments, {"query", "since", "until", "path", "limit"})
        return github_json(
            {
                "repository": repo.full_name,
                "commits": github_client.search_commits(
                    repo,
                    query=required_string(arguments, "query"),
                    since=optional_string(arguments, "since"),
                    until=optional_string(arguments, "until"),
                    path=optional_string(arguments, "path"),
                    limit=bounded_limit(arguments),
                ),
            }
        )
    if tool == "search_code":
        ensure_allowed_arguments(arguments, {"query", "path", "limit"})
        return github_json(
            {
                "repository": repo.full_name,
                "results": github_client.search_code(
                    repo,
                    query=required_string(arguments, "query"),
                    path=optional_string(arguments, "path"),
                    limit=bounded_limit(arguments),
                ),
            }
        )
    if tool == "get_commit":
        ensure_allowed_arguments(arguments, {"sha"})
        return github_json(
            {
                "repository": repo.full_name,
                "commit": github_client.get_commit(repo, sha=required_string(arguments, "sha")),
            }
        )
    if tool == "get_pull_request":
        ensure_allowed_arguments(arguments, {"number"})
        return github_json(
            {
                "repository": repo.full_name,
                "pull_request": github_client.get_pull_request(
                    repo,
                    number=required_int(arguments, "number"),
                ),
            }
        )
    raise ValueError(f"Unsupported GitHub tool: {tool}")


def configured_repository(context: "ChartDexToolContext") -> GitHubRepository:
    row = get_github_repository_for_org(context.app_db_path, context.org_id)
    if row is None:
        raise ValueError("No GitHub repository is configured for this organization")
    return GitHubRepository(owner=row["owner"], name=row["name"])


def github_json(payload: dict[str, object]) -> str:
    text = json.dumps(payload, sort_keys=True, default=str)
    if len(text) > MAX_GITHUB_TEXT_CHARS:
        return text[:MAX_GITHUB_TEXT_CHARS] + "\n... truncated by ChartDex GitHub tool output limit"
    return text


def required_string(arguments: dict[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def ensure_allowed_arguments(arguments: dict[str, object], allowed: set[str]) -> None:
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"Unsupported GitHub tool arguments: {', '.join(sorted(unknown))}")


def optional_string(arguments: dict[str, object], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def required_int(arguments: dict[str, object], key: str) -> int:
    value = arguments.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def bounded_limit(arguments: dict[str, object]) -> int:
    value = arguments.get("limit", DEFAULT_LIMIT)
    if not isinstance(value, int):
        raise ValueError("limit must be an integer")
    if value < 1:
        raise ValueError("limit must be at least 1")
    return min(value, MAX_LIMIT)


def truncate_text(value: str | None, max_chars: int) -> str | None:
    if value is None or len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n... truncated"


def first_line(value: str) -> str:
    return value.splitlines()[0] if value.splitlines() else value
