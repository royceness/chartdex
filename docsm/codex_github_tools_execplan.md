# Codex GitHub Inspection Tools

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

The controlling instructions for this plan are in `/Users/royce/.codex/.agent/PLANS.md`. This repository does not contain its own copy of that file, so this plan repeats the implementation context needed to continue work without relying on prior conversation.

## Purpose / Big Picture

After this change, a ChartDex Codex thread can answer a follow-up like "when was this revenue bug introduced?" by inspecting a single GitHub repository configured for the authenticated user's organization. Codex will not receive a GitHub token or arbitrary repository access. Instead, it will call backend-owned dynamic tools over the existing app-server stdio pipe, and the backend will proxy bounded read-only GitHub requests using server-side org configuration and credentials.

The user-visible proof is a backend test that configures the demo org's repository, asks a `github.search_commits` dynamic tool call, and observes that the fake GitHub client is called for only that configured repo. Normal Python tests should pass without network access.

## Progress

- [x] (2026-05-18 08:08+09:30) Read settings, dependency files, existing dynamic tool wiring, and the current Codex app-server adapter.
- [x] (2026-05-18 08:10+09:30) Decided to implement a single configured repository per org rather than accepting `owner/repo` from model tool arguments.
- [x] (2026-05-18 08:12+09:30) Verified that no GitHub token is present in environment, that `gh` is authenticated locally, and that authenticated API access to `royceness/acme-outdoor-demo-store` succeeds.
- [x] (2026-05-18 08:19+09:30) Added app-state storage and seeding for the one GitHub repository per org, defaulting the demo org to `royceness/acme-outdoor-demo-store`.
- [x] (2026-05-18 08:23+09:30) Added a read-only GitHub REST client and tool handler with bounded outputs.
- [x] (2026-05-18 08:24+09:30) Registered GitHub tools in the app-server dynamic tool list.
- [x] (2026-05-18 08:26+09:30) Added tests for org repo scoping, dynamic tool registration, and no-network fake GitHub behavior.
- [x] (2026-05-18 08:21+09:30) Ran backend and frontend validation.

## Surprises & Discoveries

- Observation: `backend/requirements.txt` does not include an HTTP client; only `backend/requirements-dev.txt` has `httpx`.
  Evidence: `cat backend/requirements.txt` showed FastAPI, PyJWT, pwdlib, python-multipart, and uvicorn only.

- Observation: The target demo repository is private and requires an authenticated GitHub token.
  Evidence: `gh api repos/royceness/acme-outdoor-demo-store --jq '{full_name,private,default_branch}'` returned `{"default_branch":"main","full_name":"royceness/acme-outdoor-demo-store","private":true}`, and an authenticated `curl` probe returned HTTP 200.

- Observation: An app-style backend tool call can read the target GitHub repository when `CHARTDEX_GITHUB_TOKEN` is set from the local `gh` token.
  Evidence: A Python smoke using `handle_tool_call(context, "github", "get_repository", {})` returned `{"full_name": "royceness/acme-outdoor-demo-store", "private": true}`, and `github.search_code` returned files such as `src/checkoutLogic.js`.

## Decision Log

- Decision: Use Python standard library `urllib.request` for GitHub REST calls instead of adding a runtime dependency.
  Rationale: The needed calls are small, read-only JSON GET requests. Avoiding a new dependency keeps the feature small and lowers install risk.
  Date/Author: 2026-05-18 / Codex

- Decision: Store and expose exactly one configured repository per org, and do not accept a repository selector in Codex tool arguments.
  Rationale: The user asked for a hard-coded repository and a single repo rather than a list. This improves least privilege because the model cannot request arbitrary repositories.
  Date/Author: 2026-05-18 / Codex

- Decision: Keep GitHub credentials backend-only via `CHARTDEX_GITHUB_TOKEN`.
  Rationale: This matches the metrics tool security model: Codex receives tool results, not bearer credentials.
  Date/Author: 2026-05-18 / Codex

- Decision: Use `royceness/acme-outdoor-demo-store` as the default demo repository for `org_acme`.
  Rationale: The user explicitly named this repository for the demo, and access was verified with the locally configured `gh` credential.
  Date/Author: 2026-05-18 / Codex

## Outcomes & Retrospective

Complete. The GitHub tools are implemented, can read the private demo repo when the backend receives a valid `CHARTDEX_GITHUB_TOKEN`, and are registered with app-server dynamic tools. Backend tests, frontend tests, and frontend build all pass.

## Context and Orientation

The existing Codex app-server integration is in `backend/app/codex_agent.py`, `backend/app/codex_service.py`, and `backend/app/codex_tools.py`. The app-server is a child process that communicates with FastAPI over standard input and standard output. Dynamic tools are schemas sent to app-server when a thread starts; when Codex calls a tool, the backend receives a JSON message and runs a Python handler with server-side `org_id`, `user_id`, and `thread_id`.

App-state SQLite setup and org-scoped data live in `backend/app/database.py`. Existing metrics tools resolve data through `get_metrics_provider_for_org(app_db_path, org_id)`. GitHub tools will follow the same pattern, but use a new one-repository-per-org table and a backend GitHub REST client.

## Plan of Work

Add an `org_github_repositories` table in `backend/app/database.py` with `org_id`, `owner`, and `name`. Seed the demo org from the environment variable `CHARTDEX_GITHUB_REPOSITORY` when present; otherwise seed `royceness/acme-outdoor-demo-store`. Add `get_github_repository_for_org(app_db_path, org_id)` so tools can resolve the configured repo without accepting repo ids from Codex.

Create `backend/app/github_tools.py`. Define a small `ConfiguredGitHubRepository` data class, a `GitHubClient` protocol, a standard-library `UrlLibGitHubClient`, a module-level `github_client`, tool schemas for a `github` namespace, and `handle_github_tool_call(context, tool, arguments)`. The client reads `CHARTDEX_GITHUB_TOKEN` from settings or environment and sends it as an Authorization header only to GitHub. Tool outputs must be bounded and JSON-serializable.

Update `backend/app/codex_tools.py` so `dynamic_tool_specs()` returns ChartDex metric tools plus GitHub tools, and `handle_tool_call()` dispatches the `github` namespace to `handle_github_tool_call()`.

Add tests in `backend/tests/test_api.py` or a focused new backend test file. Tests must not call real GitHub. They should monkeypatch the module-level GitHub client with a fake that records the configured repo and returns deterministic results.

## Concrete Steps

Work from `/Users/royce/.codex/worktrees/b23a/New project 3`.

Run backend tests with:

    /Users/royce/Documents/'New project 3'/.venv/bin/python -m pytest

Run frontend tests and build with:

    npm --prefix frontend test -- --run
    npm --prefix frontend run build

## Validation and Acceptance

Acceptance requires Python tests to pass without network access, frontend tests and build to still pass, and a test proving that `github.search_commits` uses the configured repository for `org_acme` without accepting a repo argument. The Codex app-server dynamic tool registration test should assert that at least one `github` namespace tool is sent in `thread/start`.

## Idempotence and Recovery

The app-state schema change uses `CREATE TABLE IF NOT EXISTS` and demo seeding uses upsert, so repeated startup should not duplicate rows. If the configured repo must change during a demo, set `CHARTDEX_GITHUB_REPOSITORY=owner/name` before starting the server with a fresh app-state database, or update the `org_github_repositories` row manually.

## Artifacts and Notes

No artifacts yet.

## Interfaces and Dependencies

In `backend/app/database.py`, add:

    def get_github_repository_for_org(app_db_path: Path, org_id: str) -> dict[str, str] | None

In `backend/app/github_tools.py`, add:

    def github_tool_specs() -> list[dict[str, object]]
    async def handle_github_tool_call(context: ChartDexToolContext, tool: str, arguments: Any) -> str

The tool namespace is `github`. Tool names are `get_repository`, `search_commits`, `search_code`, `get_commit`, and `get_pull_request`.

## Debt and Future Issues

Future production work should replace the single environment-seeded demo mapping with an admin-managed integration record backed by a GitHub App installation id. The current design is intentionally narrow for the demo and does not create Jira issues or mutate GitHub.
