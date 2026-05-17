# Codex App Server Integration

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

The controlling instructions for this plan are in `/Users/royce/.codex/.agent/PLANS.md`. This repository does not contain its own copy of that file, so this plan repeats the implementation context needed to continue work without relying on prior conversation.

## Purpose / Big Picture

After this change, ChartDex users can create Codex-backed analytics threads from the web UI, read the assistant response, and ask follow-up questions in the same Codex conversation. Codex can answer by calling ChartDex-owned read-only tools for metrics, dashboards, metric schema, business events, and structured metric queries. Codex never receives a browser cookie, a metrics database path, or arbitrary SQLite access; every tool call is resolved by the backend from the authenticated user's `org_id` and `user_id`.

The user-visible proof is: sign in, submit a question in the Codex panel or top ask box, wait for the thread to complete, then ask a follow-up from that thread. The backend stores both turns in app-state SQLite, and tests prove that unauthenticated access is rejected and another user cannot read or continue a thread they do not own.

## Progress

- [x] (2026-05-17 21:59Z) Read the existing ChartDex auth, dashboard, metrics provider, frontend Codex mock, and backend tests.
- [x] (2026-05-17 22:12Z) Inspected `/Users/royce/GitHub/syd-hackathon-04-2026` and identified its long-lived `codex app-server` subprocess adapter, follow-up support, and fake-agent tests.
- [x] (2026-05-17 22:17Z) Verified that `codex space app-server` accepts the same app-server protocol and supports per-thread `dynamicTools` plus `item/tool/call` responses.
- [x] (2026-05-17 22:20Z) Created this ExecPlan and selected a backend-owned dynamic-tool design.
- [x] (2026-05-17 22:34Z) Implemented persisted Codex threads and turns in app-state SQLite, including `org_id`, `owner_user_id`, `external_codex_thread_id`, `status`, context JSON, errors, and timestamps.
- [x] (2026-05-17 22:38Z) Implemented the Codex app-server adapter with `codex space app-server`, dynamic tool registration, dynamic tool call handling, and follow-up support.
- [x] (2026-05-17 22:41Z) Added ChartDex read-only tools for metrics, metric descriptions, dimensions, business events, experiments, dashboards, dashboard detail, and bounded structured metric queries.
- [x] (2026-05-17 22:44Z) Replaced the mocked `/api/codex/threads` route with authenticated create, list, detail, and follow-up APIs.
- [x] (2026-05-17 22:49Z) Wired the frontend ask and follow-up forms to the new APIs with polling while threads are queued or running.
- [x] (2026-05-17 22:53Z) Added backend and frontend tests for persistence, follow-ups, owner scoping, context validation, tool queries, app-server adapter dynamic tool calls, create-thread UI, and follow-up UI.

## Surprises & Discoveries

- Observation: The sibling repo path named by the user was slightly different from the spoken name.
  Evidence: `/Users/royce/GitHub/Sid-Hackathon-04-2-2026` did not exist; the matching repo was `/Users/royce/GitHub/syd-hackathon-04-2026`.

- Observation: `codex space app-server` behaves like `codex app-server` on this machine.
  Evidence: `codex space app-server --help` printed the `codex app-server` help, and a probe successfully initialized a server using `codex space app-server`.

- Observation: Dynamic tools are accepted even though the generated TypeScript type does not expose a `dynamicTools` field on `ThreadStartParams`.
  Evidence: A probe started a thread with `dynamicTools: [{ namespace: "chartdex", name: "ping", ... }]`, received `item/tool/call`, returned `{ contentItems: [{ type: "inputText", text: "pong" }], success: true }`, and Codex answered `pong`.

- Observation: The worktree did not have its own Python virtualenv or frontend dependencies installed.
  Evidence: `. .venv/bin/activate` failed and `npm --prefix frontend test -- --run` initially failed with `vitest: command not found`. The existing document checkout virtualenv at `/Users/royce/Documents/New project 3/.venv/bin/python` was used for Python tests, and `npm --prefix frontend ci` installed frontend dependencies in this worktree.

- Observation: The app-server integration can be tested without spending a full model turn by using fake agents in backend tests.
  Evidence: `backend/tests/test_api.py` monkeypatches `app.main.codex_agent` and verifies persisted external thread ids, follow-up continuation, and streamed delta replacement.

## Decision Log

- Decision: Use `codex space app-server` as the default command and keep the app-server interaction behind a Python adapter.
  Rationale: The user explicitly said this is how to boot Codex app server, and the sibling project already proved the stdio JSON-RPC pattern. Keeping it behind an adapter lets tests use a fake agent and lets future protocol changes stay localized.
  Date/Author: 2026-05-17 / Codex

- Decision: Expose ChartDex data through per-thread dynamic tools instead of giving Codex raw HTTP credentials or direct SQLite paths.
  Rationale: The backend can bind the thread to `auth.org_id` and `auth.user_id` once, then each tool handler resolves access through existing app-state provider configuration. That preserves least privilege and makes cross-org checks testable.
  Date/Author: 2026-05-17 / Codex

- Decision: Start with polling rather than Server-Sent Events for the frontend.
  Rationale: The current UI already loads `/api/codex/threads`, and the backend will persist deltas as turns. Polling is enough to demonstrate working create/follow-up behavior while leaving an SSE endpoint as a later enhancement.
  Date/Author: 2026-05-17 / Codex

- Decision: Implement structured metric querying rather than arbitrary SQL.
  Rationale: The user wants Codex to run queries, but secure query execution should be expressed through allowlisted metric keys, dimensions, filters, and time ranges. This avoids exposing a general SQL console while still letting Codex answer analytics questions.
  Date/Author: 2026-05-17 / Codex

- Decision: Persist only user and assistant turns in the browser-facing thread response, while keeping tool calls internal to app-server handling.
  Rationale: The other coordinating thread flagged raw tool turns as noisy. The UI needs readable conversation history; tool events can be added later as a compact debug view if needed.
  Date/Author: 2026-05-17 / Codex

- Decision: Validate browser-provided dashboard context against accessible dashboard detail before storing it.
  Rationale: Browser context is useful but not authoritative. The backend now checks dashboard ownership through existing org/user scoping and verifies that a provided panel and metric belong to that dashboard.
  Date/Author: 2026-05-17 / Codex

## Outcomes & Retrospective

Implemented and validated. The backend now persists Codex threads and turns in app-state SQLite, scopes every thread to the authenticated org and user, starts Codex through `codex space app-server`, registers ChartDex read-only dynamic tools, and continues existing external Codex threads for follow-ups. The frontend can submit new questions, submit follow-ups, render errors, and poll while any thread is active. Remaining future work is streaming over SSE/WebSocket and write-capable personal dashboard creation.

## Context and Orientation

The backend lives in `backend/app`. `backend/app/auth.py` creates and verifies the HttpOnly cookie JWT, returning an `AuthContext` with `user_id`, `org_id`, and `role`. `backend/app/main.py` defines FastAPI routes. `backend/app/database.py` owns app-state SQLite setup, seeded demo users and dashboards, and currently returns hardcoded `CODEX_THREADS`. `backend/app/metrics_provider.py` maps an authenticated `org_id` to a metrics provider and serves dashboard panels from the org's SQLite metrics database.

The frontend lives in `frontend/src`. `frontend/src/api.ts` defines types and API helpers. `frontend/src/App.tsx` renders the dashboard shell and a right-side Codex panel. Today the top ask input and thread follow-up form do not submit anything; the panel renders mocked threads from `GET /api/codex/threads`.

The sibling repo `/Users/royce/GitHub/syd-hackathon-04-2026` has a useful reference implementation. Its `server/review_room/agent.py` starts a long-lived app-server subprocess, sends `initialize`, `thread/start`, and `turn/start`, collects `item/agentMessage/delta`, and supports continuing a thread by saving the external Codex thread id. ChartDex will use the same protocol but add dynamic tools.

A dynamic tool is a tool definition passed to Codex when a thread starts. The app-server can later ask the client to execute that tool by sending an `item/tool/call` request over stdio. ChartDex responds to that request with text content. This lets Codex inspect ChartDex data without network access or direct database access.

## Plan of Work

First, extend `backend/app/database.py` to create `codex_threads` and `codex_turns` tables during startup. Add functions to create a thread, append turns, update status, store the external Codex app-server thread id, list accessible threads for a user, fetch one accessible thread, and append assistant deltas. All queries must filter by both `org_id` and `owner_user_id` where a user-owned thread is being read or continued.

Second, extend `backend/app/metrics_provider.py` with read-only context methods. Add methods to list metric catalog rows, list dimensions and dimension values, list business events, list experiments, and run a structured `query_metrics` request. The SQLite provider must open the metrics database read-only for normal reads. The query method should allow only known metric expressions and known dimensions, apply date and dimension filters using parameters, and limit result rows.

Third, add `backend/app/codex_tools.py`. This module defines the dynamic tool specifications and a `ChartDexToolContext` containing only `app_db_path`, `org_id`, `user_id`, and `thread_id`. It dispatches tool calls by name and serializes results to compact JSON text. Tool handlers call existing backend functions and provider methods; they never accept an `org_id` or database path argument from Codex.

Fourth, add `backend/app/codex_agent.py`. This module defines an agent protocol, a real `CodexAppServerAgent`, and a pool. The default command is `codex space app-server`, configurable by environment. The adapter starts app-server with stdio, initializes it, starts threads with ChartDex dynamic tools, handles `item/tool/call` by calling `codex_tools`, streams assistant deltas through a callback, and returns the external Codex thread id plus final Markdown. It also exposes `continue_thread` for follow-up turns.

Fifth, update `backend/app/main.py` to own an agent pool in lifespan, replace the mock `/api/codex/threads` route, and add `POST /api/codex/threads`, `GET /api/codex/threads/{thread_id}`, and `POST /api/codex/threads/{thread_id}/turns`. The create endpoint stores the user turn and schedules a background Codex run. The follow-up endpoint rejects running threads, stores another user turn, and schedules a continuation with the saved external Codex thread id.

Sixth, update `frontend/src/api.ts` and `frontend/src/App.tsx` so the top ask box creates a thread, the right panel New Thread button focuses a composer, follow-up forms post to the selected thread, and the app polls while any thread is queued or running.

Seventh, add tests. Backend tests should use a fake agent, verify create/follow-up persistence, verify tool handlers are org-scoped, verify protected routes require auth, and verify user scoping. Frontend tests should verify that submitting a question calls the create endpoint, renders the returned thread, and follow-up submits to the correct endpoint.

## Concrete Steps

Run commands from `/Users/royce/.codex/worktrees/b23a/New project 3`.

After backend edits, run:

    . .venv/bin/activate && pytest backend/tests/test_api.py

After frontend edits, run:

    npm --prefix frontend test -- --run

Run the full available test set before finishing:

    . .venv/bin/activate && pytest
    npm --prefix frontend test -- --run

In this worktree, the local `.venv` path was not present. The validation command actually used was:

    /Users/royce/Documents/New\ project\ 3/.venv/bin/python -m pytest

Frontend dependencies were installed with:

    npm --prefix frontend ci

The frontend validation commands were:

    npm --prefix frontend test -- --run
    npm --prefix frontend run build

For manual verification, start the app:

    npm run dev

Then open `http://127.0.0.1:5175/`, sign in as `admin@acme.test` with password `password`, ask "What happened to Android checkout conversion?", and observe a new Codex thread move from queued/running to complete with a Markdown response. Ask a follow-up in that same thread and observe another user turn and assistant turn appended.

## Validation and Acceptance

The backend is accepted when tests prove that Codex thread APIs require authentication, thread reads are scoped to the owning user and org, creating a thread stores a user turn and assistant turn, follow-up uses the same external Codex thread id, the app-server adapter responds to dynamic tool calls, and ChartDex tools can read dashboards and metrics only through the authenticated org's provider. This was validated with `23 passed` from the Python suite.

The frontend is accepted when tests prove that the ask box and follow-up form call the new API helpers and refresh thread state. This was validated with `5 passed` from Vitest and a successful production build. Manual API smoke validation started the FastAPI server on `127.0.0.1:8017`, confirmed `/api/health`, logged in as `admin@acme.test`, and confirmed `/api/codex/threads` returned an empty authenticated list.

## Idempotence and Recovery

Database initialization uses `CREATE TABLE IF NOT EXISTS`, so restarting the server is safe. Demo metrics generation remains deterministic and should regenerate a missing or invalid demo metrics SQLite file. If local demo state becomes confusing, delete `backend/data/app_state.sqlite3` and `data/chartdex_demo.sqlite`, then restart the backend.

Codex app-server workers are terminated during FastAPI shutdown. If a worker exits unexpectedly, the adapter starts a new process on the next request.

## Artifacts and Notes

Probe transcript excerpt proving dynamic tools:

    thread/start accepted dynamicTools with chartdex.ping
    app-server sent item/tool/call for namespace chartdex, tool ping
    client replied with contentItems inputText "pong"
    assistant delta was "pong"

The sibling project adapter reference is `/Users/royce/GitHub/syd-hackathon-04-2026/server/review_room/agent.py`.

## Interfaces and Dependencies

In `backend/app/codex_agent.py`, define:

    class CodexAgent(Protocol):
        async def run_thread(self, title: str, prompt: str, tool_context: ChartDexToolContext, on_delta: Callable[[str], Awaitable[None]] | None = None) -> CodexAgentResult: ...
        async def continue_thread(self, external_thread_id: str, prompt: str, tool_context: ChartDexToolContext, on_delta: Callable[[str], Awaitable[None]] | None = None) -> CodexAgentResult: ...

In `backend/app/codex_tools.py`, define:

    class ChartDexToolContext(BaseModel):
        app_db_path: Path
        org_id: str
        user_id: str
        thread_id: str

    def dynamic_tool_specs() -> list[dict[str, object]]
    async def handle_tool_call(context: ChartDexToolContext, namespace: str | None, tool: str, arguments: object) -> str

In `backend/app/metrics_provider.py`, extend `MetricsProvider` with read-only metadata and structured query methods.

No new production Python dependency should be needed. Existing FastAPI background tasks and Python `asyncio` are sufficient.

## Debt and future issues

Server-Sent Events or WebSocket streaming is intentionally left for a future issue. The first implementation persists deltas and polls from the frontend because it is smaller and testable.

Codex-created dashboards are out of scope for this plan. The initial tools are read-only. A future plan can add `dashboards:write:personal` with explicit role and ownership checks.

Revision note, 2026-05-17: Initial plan created after inspecting the sibling app-server integration and validating dynamic tool calls locally.

Revision note, 2026-05-17: Updated progress, decisions, validation, and outcomes after implementing the backend adapter, tool layer, persisted API, frontend wiring, and tests.
