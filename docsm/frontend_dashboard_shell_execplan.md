# Frontend Dashboard Shell With Codex Threads

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows the ExecPlan guidance in `/Users/royce/.codex/.agent/PLANS.md`. This document is self-contained so a future contributor can restart the frontend shell work without relying on conversation history.

## Purpose / Big Picture

After this change, signing in to ChartDex shows the intended product shell rather than the early scaffold. A user sees org dashboards and personal dashboards in a left navigation area, the selected dashboard with multiple metric panels in the center, and Codex investigation threads in a right-side accordion. The thread bodies render Markdown now, with a component boundary ready for Mermaid fenced-code rendering later. The dashboard panels use mock data served by the FastAPI backend so the frontend has the right shape while the richer metrics database is developed in another worktree.

## Progress

- [x] (2026-05-17 21:16Z) Read PLANS.md and created this ExecPlan.
- [x] (2026-05-17 21:16Z) Inspected sibling project `/Users/royce/GitHub/syd-hackathon-04-2026` for thread rendering, Markdown, and Mermaid component shape.
- [x] (2026-05-17 21:49Z) Added backend mock API shape for dashboard navigation, selected dashboard panels, and Codex threads.
- [x] (2026-05-17 21:49Z) Added frontend dependencies for Markdown rendering.
- [x] (2026-05-17 21:53Z) Replaced the current post-login dashboard view with a three-region application shell.
- [x] (2026-05-17 21:53Z) Added chart panel selection state so click-drag time ranges can later become Codex/voice context.
- [x] (2026-05-17 21:53Z) Rendered Codex threads as accordions with Markdown turns and a follow-up input.
- [x] (2026-05-17 21:54Z) Added or updated tests for authenticated dashboard shell rendering and Markdown output.
- [x] (2026-05-17 21:55Z) Ran backend tests, frontend tests, frontend build, and browser smoke verification.

## Surprises & Discoveries

- Observation: The sibling project uses `react-markdown` and a custom `MermaidBlock` component to intercept `language-mermaid` fenced code blocks.
  Evidence: `/Users/royce/GitHub/syd-hackathon-04-2026/web/src/components/AIWorkbench.tsx` renders `ReactMarkdown` with a custom `code` component, and `/Users/royce/GitHub/syd-hackathon-04-2026/web/src/components/MermaidBlock.tsx` dynamically imports `mermaid`.

- Observation: `react-markdown` wraps fenced code blocks in `pre`, so returning a block component from the `code` override nests a `div` inside `pre`.
  Evidence: The first frontend test run showed the Mermaid placeholder rendered inside a `pre`. The implementation now handles Mermaid in the `pre` component override and leaves inline code rendering in the `code` override.

## Decision Log

- Decision: Use backend-served mock data rather than hardcoding all dashboard and Codex thread content in React.
  Rationale: The richer metrics database is being developed separately, but the frontend should already consume API shapes that can later be backed by real data without another UI rewrite.
  Date/Author: 2026-05-17 / Codex

- Decision: Use `react-markdown` and `remark-gfm` for thread body rendering now, while keeping Mermaid as an explicit fenced-code extension point.
  Rationale: This matches the working sibling project and supports future streaming because thread content can update as Markdown strings without changing the renderer.
  Date/Author: 2026-05-17 / Codex

- Decision: Keep Recharts for the first interactive chart panels.
  Rationale: Recharts is already installed, supports line and bar charts, and has mouse event primitives that are sufficient for a hackathon-grade click-drag time range selection. A later switch to ECharts or visx remains possible if richer interactions become necessary.
  Date/Author: 2026-05-17 / Codex

- Decision: Render Mermaid fenced blocks as a clearly labeled placeholder for this slice, rather than installing `mermaid` immediately.
  Rationale: The user explicitly said Mermaid rendering can be skipped for now, but the thread renderer should be shaped so real rendering is a component swap later.
  Date/Author: 2026-05-17 / Codex

## Outcomes & Retrospective

Implemented and validated. Signing in now shows the three-region ChartDex shell with org and personal dashboard navigation, a selected dashboard with multiple panels, and a right-side Codex thread accordion. Thread turns render Markdown through `react-markdown` and `remark-gfm`, and fenced Mermaid blocks render as diagram-ready placeholders. Backend mock endpoints are protected by auth and provide dashboard detail plus Codex thread data. Future work remains to replace mock dashboard/thread data with real metrics/Codex persistence and to swap the Mermaid placeholder for actual Mermaid rendering.

## Context and Orientation

The current project lives at `/Users/royce/Documents/New project 3`. The backend is a FastAPI app under `backend/app`. It already has cookie-backed JWT auth in `backend/app/auth.py`, auth routes in `backend/app/routes/auth.py`, and SQLite setup in `backend/app/database.py`. The current frontend is a Vite React app under `frontend/src`. `frontend/src/App.tsx` currently handles sign-in and then shows a simple org dashboard list plus one revenue line chart. `frontend/src/api.ts` contains cookie-aware fetch helpers.

A “Codex thread” in this plan means a persisted investigation conversation that will eventually be backed by `codex app-server`. For this milestone it is mock data returned by the backend. A “panel” means one chart or visualization inside a dashboard, such as a revenue line chart, conversion line chart, platform bar chart, or checkout funnel.

## Plan of Work

First, update backend types and endpoints in `backend/app/main.py` and `backend/app/database.py` so the authenticated frontend can request a richer dashboard payload and mock Codex threads. The current protected `/api/dashboards` endpoint should continue to return dashboard summaries, but summaries should include both org and personal dashboards. Add `GET /api/dashboards/{dashboard_id}` to return one selected dashboard with panels. Add `GET /api/codex/threads` to return mock thread data. These routes must still depend on `require_auth`.

Second, add `react-markdown` and `remark-gfm` to the frontend dependencies. Create small frontend types in `frontend/src/api.ts` for dashboard summaries, dashboard detail, dashboard panels, chart selections, Codex threads, and Codex turns. Add API helpers for `fetchDashboardDetail` and `fetchCodexThreads`.

Third, replace the authenticated branch of `frontend/src/App.tsx` with a three-column shell. Keep the login screen and logout behavior. The left sidebar lists org dashboards and personal dashboards. The center renders the selected dashboard title, time range display, chart panels, and an add-panel placeholder. The right pane renders Codex threads as accordions. The follow-up box can be local-only for now; it should not pretend to call Codex until the backend exists.

Fourth, implement chart selection state for line charts. A user should be able to mouse down on one date, drag to another date, and release. The UI should show the selected panel and date range. This state will later feed voice and Codex context, but for this milestone it only needs to be visible and structured in React.

Fifth, update tests. Backend tests should prove unauthenticated users cannot read dashboard detail or Codex threads, and authenticated users can. Frontend tests should prove login leads to the shell, dashboard navigation renders panel content, Markdown thread content renders, and a Mermaid fenced block appears as a clearly marked placeholder or code block until real Mermaid rendering is enabled.

## Concrete Steps

Run commands from `/Users/royce/Documents/New project 3`.

Install frontend dependencies after editing `frontend/package.json`:

    npm --prefix frontend install

Run validation:

    . .venv/bin/activate && pytest backend
    npm test
    npm --prefix frontend run build

Start the app for manual verification:

    npm run dev

Open `http://127.0.0.1:5175/`, sign in as `admin@acme.test` with password `password`, and verify that the three-region shell appears.

## Validation and Acceptance

The change is accepted when an authenticated user can sign in and observe org dashboards, personal dashboards, a selected dashboard with multiple chart panels, and a right-side Codex thread accordion. At least one Codex thread must render Markdown with headings, lists, and a fenced `mermaid` block represented by a future-ready component path. Tests must pass with backend and frontend commands listed above. The frontend build warning about large chunks is acceptable for now because Recharts is already part of the app and this is a hackathon demo.

## Idempotence and Recovery

All backend seed data remains idempotent and local SQLite files are ignored by Git. If local data gets into a confusing state, stop the dev server, delete `backend/data`, and restart `npm run dev`; startup will recreate demo data. If frontend dependencies are out of sync, rerun `npm --prefix frontend install`.

## Artifacts and Notes

The sibling project shows the preferred thread renderer pattern:

    ReactMarkdown components.code checks className for language-mermaid.
    Mermaid rendering is isolated in a MermaidBlock component.
    Thread accordions keep open state in a Set of thread IDs.

## Interfaces and Dependencies

Frontend dependencies to add:

    react-markdown
    remark-gfm

Backend response shapes to expose:

    DashboardSummary: id, name, space, description
    DashboardDetail: id, name, space, description, time_range_label, panels
    DashboardPanel: id, title, type, metric_key, data
    CodexThread: id, title, status, turns
    CodexTurn: id, role, markdown, created_at

## Debt and Future Issues

Mermaid rendering will be added after the shell lands. The frontend should be structured so this is a component swap rather than a data model change. Streaming Codex responses will also be future work; the thread model should use ordered turns so streaming can update the latest assistant turn without replacing the entire right pane.

Revision note, 2026-05-17: Initial ExecPlan created after inspecting the sibling Review Room project and confirming its `react-markdown` plus custom Mermaid component approach.

Revision note, 2026-05-17: Updated progress, discoveries, decisions, and outcomes after implementing and validating the dashboard shell.
