# Persist Codex Threads Behind Authenticated Browser APIs

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows the requirements in `/Users/royce/.codex/.agent/PLANS.md`.

## Purpose / Big Picture

ChartDex needs the right browser-facing shape for Codex investigations before the external Codex app-server work is finished in another worktree. After this change, a signed-in user can create a Codex thread from the top ask box, see persisted thread turns in the right-hand panel, send follow-up turns, and have every thread scoped to the authenticated user's organization and user id. The implementation keeps the browser API stable while hiding the execution backend behind a small provider boundary that can later call the real Codex app-server.

## Progress

- [x] (2026-05-17T21:58:29Z) Created this ExecPlan with the target browser API, persistence model, validation rules, frontend behavior, and acceptance criteria.
- [x] (2026-05-17T22:05:00Z) Replaced the in-memory `CODEX_THREADS` mock in `backend/app/database.py` with SQLite `codex_threads` and `codex_turns` tables scoped by `org_id` and `owner_user_id`.
- [x] (2026-05-17T22:12:00Z) Added backend routes for listing, creating, fetching, and appending to Codex threads, including context validation against authorized dashboard and panel data.
- [x] (2026-05-17T22:12:00Z) Added a local Codex execution provider that marks queued threads as complete with deterministic assistant markdown until the external app-server provider is available.
- [x] (2026-05-17T22:16:00Z) Added dashboard and panel descriptions intended for agents to the dashboard API so voice and Codex tools can load the hierarchy without guessing.
- [x] (2026-05-17T22:26:00Z) Wired the frontend top ask box, right-panel new thread/follow-up forms, and polling while queued/running threads exist.
- [x] (2026-05-17T22:38:00Z) Added backend and frontend tests, then ran backend tests, frontend tests, frontend build, and a browser smoke check.

## Surprises & Discoveries

- Observation: Seeded `queued` and `running` demo threads caused the frontend to poll forever immediately after login.
  Evidence: Browser smoke test showed seeded threads with active statuses before any new user action, so the status-based polling loop had no natural stop condition.

- Observation: FastAPI `BackgroundTasks` let the create route return the queued thread payload while still completing the local demo executor in the same test/client lifecycle.
  Evidence: Backend test `test_creates_codex_thread_with_validated_context` receives `status == "queued"` from `POST /api/codex/threads`, then `GET /api/codex/threads/{thread_id}` returns `status == "complete"`.

## Decision Log

- Decision: Persist Codex thread state in the existing app-state SQLite database rather than the metrics SQLite database.
  Rationale: Threads are application state owned by a user and org, while metrics data is the provider-specific analytical data source. Keeping them separate preserves the existing separation between app state and metrics state.
  Date/Author: 2026-05-17 / Codex

- Decision: The first implementation will use a local deterministic execution provider through the same provider boundary that the external Codex app-server can replace.
  Rationale: The browser API and frontend can be exercised end-to-end before the parallel app-server work lands, while keeping the integration point explicit and small.
  Date/Author: 2026-05-17 / Codex

- Decision: Browser-supplied context is treated as a hint and revalidated server-side against the authenticated user's dashboards and panels.
  Rationale: A JWT cookie proves who the user is, but it does not make arbitrary dashboard or panel ids from the browser trustworthy. The backend must derive `org_id` from `AuthContext` and verify dashboard ownership and panel membership itself.
  Date/Author: 2026-05-17 / Codex

- Decision: Seeded Codex threads are all completed.
  Rationale: The polling rule is status-based, so seeded active threads would make the app poll forever on initial load. Newly created or followed-up threads still exercise queued/running behavior.
  Date/Author: 2026-05-17 / Codex

## Outcomes & Retrospective

Implemented the authenticated browser API and frontend flow for persisted Codex threads. Threads and turns now live in the app-state SQLite database with org/user scoping, context snapshots, statuses, timestamps, and optional error messages. The browser can create threads from the top ask box or the right panel, send follow-ups, and poll while threads are active. The executor is currently a local deterministic provider that proves the API and UI behavior; the external Codex app-server provider remains future work behind the provider boundary.

## Context and Orientation

The backend lives under `backend/app`. `backend/app/main.py` defines the FastAPI routes and currently exposes `GET /api/codex/threads` by returning an in-memory list from `backend/app/database.py`. `backend/app/auth.py` provides `AuthContext` and `require_auth`, which read the HttpOnly JWT cookie and identify the current `user_id`, `org_id`, and role. `backend/app/database.py` initializes the app-state SQLite database, seeds users and dashboards, and calls the org metrics provider for dashboard details. `backend/app/metrics_provider.py` reads the metrics SQLite database and returns dashboard panels.

The frontend lives under `frontend/src`. `frontend/src/api.ts` defines TypeScript types and fetch helpers. `frontend/src/App.tsx` renders the three-pane application, including the top ask input and the right-hand Codex thread accordion. The thread UI currently renders existing thread turns, but the top ask input and follow-up form do not call the backend yet.

The term "Codex thread" in this plan means a persisted ChartDex record representing one investigation or authoring conversation. It can later map to an external Codex app-server thread through an `external_thread_id`, but the browser only sees the local ChartDex thread id. The term "turn" means one message in the conversation, such as a user question or assistant markdown response.

## Plan of Work

First, update `backend/app/database.py` to create `codex_threads` and `codex_turns` tables during `initialize_databases`. Add helper functions to serialize one thread with ordered turns, list threads for `org_id` and `owner_user_id`, create a thread with the first user turn, append a follow-up turn, and update status plus assistant turns. Seed a small set of demo threads for the two demo users so the right panel is populated after login without relying on module-level memory.

Second, add `backend/app/codex_service.py`. This module will define request context validation and a `LocalDemoCodexProvider` with an `execute_thread_turn` method. The provider will mark a queued thread as running, read the current thread and context, append a concise assistant markdown response, and mark the thread complete. This provider is intentionally deterministic and local; the later external provider should keep the same call shape but delegate to Codex app-server.

Third, update `backend/app/main.py` with `POST /api/codex/threads`, `GET /api/codex/threads/{thread_id}`, and `POST /api/codex/threads/{thread_id}/turns`. These routes will use `require_auth`, never accept `org_id`, and pass `auth.org_id` plus `auth.user_id` into database functions. Creating and following up will schedule the provider through FastAPI `BackgroundTasks` so the immediate response can show `queued`.

Fourth, enrich the dashboard API with agent descriptions. `backend/app/metrics_provider.py` should include `agent_description` on dashboard detail and on every panel. `backend/app/database.py` should add `agent_description` to dashboard summaries returned by `list_dashboards` and `get_dashboard_summary`. These descriptions should be human-readable paragraphs explaining what the dashboard or panel is for.

Fifth, update `frontend/src/api.ts` with request helpers and types for Codex context and thread create/follow-up. Update `frontend/src/App.tsx` so the top ask form creates a thread with current dashboard and chart selection context, the right panel can create a new thread and send follow-ups, and the app polls `GET /api/codex/threads` every two seconds only while any thread is queued or running.

Finally, update tests. Backend tests should verify authenticated thread creation, user/org scoping, context validation, follow-up conflicts while running, and protected routes. Frontend tests should verify the top ask box posts a thread, polling refreshes active threads, and follow-up submission calls the new endpoint.

## Concrete Steps

Run all commands from `/Users/royce/Documents/New project 3` unless a subdirectory is explicitly named.

After backend edits, run:

    . .venv/bin/activate && pytest backend tests

After frontend edits, run:

    npm test -- --run
    npm --prefix frontend run build

For browser verification, start or reuse the local dev servers, sign in as `admin@acme.test` with password `password`, submit a question in the top ask box, and observe a new thread in the right panel.

## Validation and Acceptance

Acceptance requires these observable behaviors:

The backend rejects unauthenticated Codex thread routes with HTTP 401. A signed-in admin can `POST /api/codex/threads` with a valid `dashboard_id`, `panel_id`, `metric_key`, and date range, receives a thread whose initial status is `queued`, and later sees the same thread with user and assistant turns. The backend returns HTTP 404 when another user tries to fetch a thread they do not own. The backend returns HTTP 400 when browser context names a panel that does not belong to the dashboard. The backend returns HTTP 409 when a follow-up is posted to a thread already queued or running.

The frontend sends top ask submissions to `POST /api/codex/threads`, includes current dashboard and chart selection context when present, and refreshes the thread list. It polls only while at least one thread is queued or running. The right-hand thread accordion renders assistant markdown and sends follow-up submissions to `POST /api/codex/threads/{thread_id}/turns`.

## Idempotence and Recovery

Database initialization must be idempotent. `CREATE TABLE IF NOT EXISTS` and `ON CONFLICT` seed statements should allow the server to restart without duplicating users, dashboards, seeded threads, or seeded turns. If local generated SQLite files need to be reset during development, they are ignored by git and can be deleted; the next app startup in demo mode recreates them.

Manual code edits should be made with `apply_patch`. Do not reset or revert unrelated work. If tests fail, fix forward and keep this ExecPlan updated with the observed failure and resolution.

## Artifacts and Notes

Validation completed:

    . .venv/bin/activate && pytest backend tests
    21 passed in 30.01s

    npm test -- --run
    Test Files  1 passed (1)
    Tests  5 passed (5)

    npm --prefix frontend run build
    built successfully with the existing Vite chunk-size warning

Browser smoke test at `http://127.0.0.1:5175/` confirmed that a top ask submission creates a persisted thread, completes through the local provider, and renders the user and assistant turns in the right panel.

## Interfaces and Dependencies

The browser API must expose:

    GET /api/codex/threads
    POST /api/codex/threads
    GET /api/codex/threads/{thread_id}
    POST /api/codex/threads/{thread_id}/turns

All routes require `AuthContext = Depends(require_auth)`. Request bodies use JSON. The create request has `title`, `utterance`, and optional `context`. The follow-up request has `utterance`.

The local thread context shape is:

    dashboard_id?: string
    panel_id?: string
    metric_key?: string
    range_start?: string
    range_end?: string

The backend database module must expose functions with this practical shape:

    list_codex_threads(app_db_path, org_id, user_id)
    get_codex_thread(app_db_path, thread_id, org_id, user_id)
    create_codex_thread(app_db_path, org_id, user_id, title, utterance, context)
    append_codex_user_turn(app_db_path, thread_id, org_id, user_id, utterance)
    update_codex_thread_status(app_db_path, thread_id, status, error_message=None)
    append_codex_assistant_turn(app_db_path, thread_id, markdown)

The frontend API module must expose:

    createCodexThread(request)
    appendCodexThreadTurn(threadId, request)
    fetchCodexThread(threadId)

## Debt and Future Issues

The local deterministic Codex execution provider is temporary. When the external Codex app-server API lands, replace the provider internals with the real JSON-RPC/app-server client while preserving the browser API and app-state authorization rules. No GitHub issue has been created yet because this is active hackathon implementation work in the current branch.

Revision note, 2026-05-17: Initial plan created to coordinate the persisted authenticated Codex thread API and frontend wiring before external Codex app-server integration lands.

Revision note, 2026-05-17: Updated after implementation to record completed backend persistence, routes, frontend wiring, tests, browser verification, and the seeded-thread polling discovery.
