# Add Realtime Voice Navigation to ChartDex

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows the requirements in `/Users/royce/.codex/.agent/PLANS.md`.

## Purpose / Big Picture

ChartDex should let a signed-in user control the dashboard shell by voice. After this change, the app has a visible voice launcher that connects through a backend `/api/realtime/session` proxy, keeps the OpenAI API key out of the browser, and exposes narrow app-owned tools for reading dashboard context, opening dashboards, focusing panels, and clearing chart selection. The first pass focuses on navigation and context awareness, not dashboard authoring or Codex investigation execution.

## Progress

- [x] (2026-05-17T22:11:20Z) Created this ExecPlan after inspecting the official `openai/realtime-voice-component` source and integration docs.
- [x] (2026-05-17T22:18:00Z) Vendored the realtime voice component source into the frontend with the Apache-2.0 license preserved and added its `zod` dependency.
- [x] (2026-05-17T22:25:00Z) Added a protected FastAPI `/api/realtime/session` endpoint that proxies the browser's multipart SDP/session request to `https://api.openai.com/v1/realtime/calls` using a server-side API key from environment or `~/.env`.
- [x] (2026-05-17T22:36:00Z) Added frontend voice adapter/tools that expose current dashboard hierarchy, selected dashboard, focused panel, and chart range selection.
- [x] (2026-05-17T22:42:00Z) Mounted a `VoiceControlWidget` in the ChartDex shell and wired tools to existing handlers for opening dashboards, focusing panels, and clearing selections.
- [x] (2026-05-17T22:48:00Z) Added backend and frontend tests, then ran backend tests, frontend tests, frontend build, and a browser smoke check.
- [x] (2026-05-17T22:11:20Z) Tuned voice behavior after live testing: less eager VAD, no response interruption, post-tool response enabled, and full dashboard/panel hierarchy embedded into session instructions so cross-dashboard panel requests can call `focus_panel` directly.
- [x] (2026-05-17T22:49:00Z) Ported the sibling project's tool-oriented realtime behavior: added a no-op tool for unclear audio and required tool calls so navigation requests should resolve to concrete app actions instead of stopping after context lookup.
- [x] (2026-05-17T22:52:00Z) Tightened normal voice confirmations to one-word responses and reset the dashboard scroll container to the top on dashboard navigation.

## Surprises & Discoveries

- Observation: The official realtime voice component is currently a GitHub reference implementation and is not published as a normal npm package.
  Evidence: `/tmp/realtime-voice-component/package.json` has `"private": true`, and the README says it is not currently published to npm.

- Observation: The sibling project path mentioned by the user was not discoverable under `/Users/royce/Documents` with the expected names.
  Evidence: Searches for `Sidhackathon04-2`, `hackathon04`, and realtime voice symbols found no matching sibling project outside the current repo. This plan proceeds from the official component source.

- Observation: JSDOM does not provide `window.matchMedia`, which the vendored widget and ghost cursor use.
  Evidence: Frontend tests initially failed with `TypeError: window.matchMedia is not a function` from `useGhostCursor.ts`. The test setup now provides a minimal `matchMedia` stub.

- Observation: Loading all dashboard details up front changed the frontend fetch sequence.
  Evidence: Existing frontend tests expected one dashboard detail request before threads. The app now requests details for every listed dashboard so the voice agent has panel hierarchy for navigation.

- Observation: The voice model was sometimes calling `get_chartdex_context` and stopping instead of using a second tool call to navigate.
  Evidence: Live testing showed requests such as "show purchases by platform" could produce context lookup behavior without the follow-up navigation. The fix embeds the full hierarchy in the session instructions, explicitly tells the model to call `focus_panel`, and enables `postToolResponse` so context tool results can lead to a follow-up tool call.

- Observation: The sibling project uses a stricter tool-first voice policy.
  Evidence: `/Users/royce/.codex/worktrees/0926/syd-hackathon-04-2026/web/src/components/VoiceSelectionDemo.tsx` configures `postToolResponse: true`, `toolChoice: "required"`, and a no-action tool for unclear audio. ChartDex now uses the same tool-choice pattern while keeping audio output enabled for brief confirmations.

## Decision Log

- Decision: Vendor the component source locally instead of depending on an unpublished package path.
  Rationale: A local `/tmp` checkout cannot be committed as a dependency, and the package is private/not published. Vendoring keeps the project bootable from the repository while preserving the upstream license.
  Date/Author: 2026-05-17 / Codex

- Decision: Use a protected `/api/realtime/session` endpoint with cookie auth.
  Rationale: The browser already has an HttpOnly session cookie, and the user explicitly required no OpenAI API keys in the browser. The backend derives identity from `AuthContext` and proxies the WebRTC session request with the server-side API key.
  Date/Author: 2026-05-17 / Codex

- Decision: Voice tools remain app-owned navigation tools.
  Rationale: The voice agent should change visible UI by calling the same React handlers the user already uses, not by manipulating arbitrary DOM or creating Codex threads for simple navigation.
  Date/Author: 2026-05-17 / Codex

## Outcomes & Retrospective

Implemented the first voice-navigation slice. The app now vendors the official realtime voice component source, exposes a protected backend session proxy, renders the voice launcher, and registers tools for reading ChartDex context, opening dashboards, focusing panels, and clearing chart selections. The implementation does not yet start Codex investigations from voice; that remains future work once the external Codex app-server provider is ready.

After live testing, the voice session now includes a less eager `server_vad` configuration with `interruptResponse: false`, a higher VAD threshold, and longer silence duration. The realtime session instructions now include the complete dashboard/panel hierarchy with ids and metric keys, so the model does not need to search for basic context before navigating. `postToolResponse` is enabled so a context tool call can be followed by the actual navigation tool call.

After comparing the sibling voice implementation, ChartDex also now requires a tool call on each realtime turn and exposes `no_action_required_or_unclear_audio` for noise or unrelated speech. The agent still owns semantic matching from the full workspace hierarchy; the app only executes explicit tools such as `focus_panel`.

Voice navigation is now intentionally terse for normal actions: successful dashboard and panel navigation should answer with "Done", "Got it", or "OK" unless the user explicitly asks for an explanation. Dashboard-level navigation now resets the center dashboard scroll container to the top so switching dashboards does not preserve a previous deep scroll position.

## Context and Orientation

The backend is a FastAPI app in `backend/app/main.py` with cookie-backed JWT auth in `backend/app/auth.py`. The current app has protected dashboard and Codex thread APIs. The frontend is a Vite React app in `frontend/src/App.tsx` with a three-pane shell: dashboard navigation on the left, dashboard panels in the center, and Codex threads on the right.

The realtime voice component is a React/browser controller and widget from `https://github.com/openai/realtime-voice-component`. It creates a WebRTC offer in the browser, posts a multipart request containing `sdp` and `session` to a server endpoint, receives an SDP answer, and then uses registered function tools to make app-owned UI changes.

In this plan, "voice tool" means a function the Realtime model can call. Each tool is narrow and explicit, such as `open_dashboard` or `focus_panel`. "Agent context" means the structured state the voice agent can inspect: dashboards, panels, current dashboard, focused panel, and selected chart range.

## Plan of Work

First, copy the official component source into `frontend/src/vendor/realtime-voice-component`, copy the license, and import the component's CSS from the app entry point. Add `zod` to `frontend/package.json` because `defineVoiceTool` requires Zod schemas.

Second, extend backend settings with `openai_api_key`, loaded from `OPENAI_API_KEY`, `CHARTDEX_OPENAI_API_KEY`, or a simple `~/.env` parser. Add `POST /api/realtime/session` to `backend/app/main.py`. The route depends on `require_auth`, reads the raw request body and `Content-Type`, forwards it to `https://api.openai.com/v1/realtime/calls` with `Authorization: Bearer <api key>`, and returns the upstream response body and content type. Tests should verify unauthenticated access fails and that missing API key returns a clear server error.

Third, add a small frontend voice layer under `frontend/src/voice`. The adapter reads latest app state through refs and exposes methods for `getContext`, `openDashboard`, `focusPanel`, and `clearSelection`. Tools built with `defineVoiceTool` call those adapter methods. `openDashboard` reuses the existing `onSelectDashboard` path. `focusPanel` scrolls the actual panel element into view and records focused panel state. The context payload must preserve hierarchy: dashboards contain panels, and current selection belongs under the current dashboard.

Fourth, mount a `ChartDexVoiceAgent` from `DashboardShell`. It should use `createVoiceControlController`, `VoiceControlWidget`, and `GhostCursorOverlay` from the vendored component. Configure it for `activationMode: "vad"`, `outputMode: "audio"` or `"text+audio"` so it can speak short confirmations, `auth.sessionEndpoint: "/api/realtime/session"`, and `auth.sessionRequestInit.credentials: "include"`. Instructions should tell the agent to speak only brief confirmations unless asked for explanation, and to use tools for navigation.

Fifth, update tests. Backend tests cover auth/missing-key behavior. Frontend tests mock the vendored voice component so the dashboard shell can be tested without microphone/WebRTC, and verify the voice context includes dashboards with panel hierarchy. Because actual microphone/WebRTC cannot be automated reliably in CI, browser smoke verification should confirm the widget is visible and the rest of the app still loads.

## Concrete Steps

Run commands from `/Users/royce/Documents/New project 3`.

Install the frontend dependency:

    npm --prefix frontend install zod

Run backend and frontend verification:

    . .venv/bin/activate && pytest backend tests
    npm test -- --run
    npm --prefix frontend run build

Use the in-app browser at `http://127.0.0.1:5175/` to verify the dashboard loads and the voice launcher is mounted. A full live voice connection requires a valid `OPENAI_API_KEY` in the backend environment or `~/.env` and browser microphone permission.

## Validation and Acceptance

The backend must return HTTP 401 for unauthenticated `POST /api/realtime/session`. With an authenticated cookie but no API key, it must return HTTP 500 with a clear message that the API key is not configured. The route must not expose the API key in response bodies.

The frontend must render a voice launcher in the dashboard shell. The voice tools must provide a context payload containing workspace dashboards and panel lists, current dashboard, focused panel, and chart selection. Calling the tool implementation for `open_dashboard` must select the dashboard through the existing handler. Calling `focus_panel` must scroll the requested panel into view when it belongs to the current dashboard.

The full test suite and build must pass. Browser smoke must show the existing dashboard and the voice launcher together.

## Idempotence and Recovery

Vendored component files should be copied from the official repo source and left untouched except for project-local import paths if needed. If a copy step is interrupted, delete `frontend/src/vendor/realtime-voice-component` and repeat the copy from `/tmp/realtime-voice-component/src`. Backend session proxy changes are additive and safe to rerun. Avoid committing generated SQLite files or build output.

## Artifacts and Notes

Validation completed:

    . .venv/bin/activate && pytest backend tests
    23 passed in 32.30s

    npm test -- --run
    Test Files  2 passed (2)
    Tests  8 passed (8)

    npm --prefix frontend run build
    built successfully with the existing Vite chunk-size warning

Browser smoke test at `http://127.0.0.1:5175/` confirmed that the dashboard loads and the voice launcher is visible. A direct unauthenticated `POST /api/realtime/session` returned HTTP 401.

## Interfaces and Dependencies

Backend route:

    POST /api/realtime/session

The route uses `AuthContext = Depends(require_auth)`. It reads the request body as bytes and forwards it to OpenAI with the incoming `Content-Type`.

Frontend voice adapter shape:

    getContext(): ChartDexVoiceContext
    openDashboard(dashboardId: string): Promise<{ ok: true; dashboardId: string }>
    focusPanel(panelId: string): Promise<{ ok: true; panelId: string }>
    clearSelection(): { ok: true }

Voice tools:

    get_chartdex_context()
    open_dashboard({ dashboard_id })
    focus_panel({ panel_id })
    clear_chart_selection()

## Debt and Future Issues

The vendored component should eventually be replaced with a normal package dependency if the upstream project becomes published or if this repo adopts a monorepo/submodule strategy. No GitHub issue has been created because this remains active hackathon implementation work.

Future voice tools should start Codex investigations through the persisted Codex thread API once the external Codex app-server provider is ready.

Revision note, 2026-05-17: Initial voice navigation integration plan created after committing the separate Codex thread API work.

Revision note, 2026-05-17: Updated after implementation to record vendoring, backend session proxy, frontend tools/widget wiring, tests, and browser smoke verification.

Revision note, 2026-05-17: Updated after live voice testing to record VAD/barge-in tuning and cross-dashboard panel navigation prompt/tool fixes.
