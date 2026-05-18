# Wire Voice to Codex Threads

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are kept up to date as work proceeds. This document follows `/Users/royce/.codex/.agent/PLANS.md`.

## Purpose / Big Picture

ChartDex voice should be able to hand deeper metric questions to the asynchronous Codex thread backend. After this change, the voice agent can create a Codex investigation with the current dashboard/panel/range context, list existing investigations, read full thread markdown, add follow-up turns, and open a thread in the right panel. When a queued/running thread completes while voice is connected, the voice agent should be notified so it can briefly tell the user and summarize from the thread text.

## Progress

- [x] (2026-05-18T09:02:00+09:30) Created this ExecPlan and inspected the existing voice adapter, Codex panel state, and Codex API helpers.
- [x] (2026-05-18T09:05:00+09:30) Implemented voice Codex tools and UI focus wiring.
- [x] (2026-05-18T09:06:00+09:30) Added completed-thread transition detection and realtime session notification.
- [x] (2026-05-18T09:07:00+09:30) Added focused frontend tests and ran verification.

## Surprises & Discoveries

- Observation: Codex thread open/collapse state currently lives inside `CodexPanel`, while the voice launcher is a sibling in the dashboard header.
  Evidence: `CodexPanel` owns `openThreadIds` and `activeThreadId`; `ChartDexVoiceAgent` is rendered beside the top ask box.

- Observation: The realtime controller can receive app-originated system messages.
  Evidence: The vendored component exposes `sendClientEvent` and the upstream docs show `conversation.item.create` with a system message followed by `requestResponse`.

## Decision Log

- Decision: Voice tools will call the existing frontend handlers rather than new browser APIs.
  Rationale: The app already scopes Codex requests through authenticated backend endpoints and attaches the current dashboard context. Reusing those handlers keeps permissions and persistence behavior unchanged.
  Date/Author: 2026-05-18 / Codex

- Decision: Thread opening will be coordinated by a request prop instead of moving the whole accordion state to the app root.
  Rationale: This keeps the state change small while still allowing voice to open/focus a right-panel thread.
  Date/Author: 2026-05-18 / Codex

## Outcomes & Retrospective

Voice can now create Codex investigations, list thread summaries, read full thread markdown, add follow-up turns, and open/focus a thread in the Codex panel. The voice context includes Codex thread summaries so the model can refer to existing investigations. The realtime session is notified when a running/queued thread transitions to complete or failed while voice is connected; the notification instructs the model to call `get_codex_thread` before briefly summarizing findings.

Verification completed:

    npm test
    9 passed

    npm --prefix frontend run build
    built successfully with the existing Vite chunk-size warning

Browser smoke at `http://127.0.0.1:5175/` confirmed the ChartDex shell, Codex panel, and Voice control render after the integration.

## Context and Orientation

The frontend voice layer is in `frontend/src/voice`. `ChartDexVoiceAgent` registers tools from `chartdexVoice.ts`. Dashboard state and Codex thread polling live in `frontend/src/App.tsx`. Existing Codex APIs are typed in `frontend/src/api.ts`: create, list, fetch one, and append a turn.

The backend Codex thread execution is asynchronous. Creating or appending a thread returns a queued/running thread, and the app polls `/api/codex/threads` while any thread is queued or running.

## Plan of Work

First, extend the voice adapter and tools with `create_codex_investigation`, `list_codex_threads`, `get_codex_thread`, `add_codex_thread_turn`, and `open_codex_thread`. Keep the current navigation tools intact.

Second, make `handleCreateCodexThread` and `handleAppendCodexTurn` return the updated `CodexThread` so voice tool calls can return thread ids/statuses. Existing forms can ignore the returned value.

Third, add a small focus request path from `DashboardShell` to `CodexPanel`, so voice can expand and mark a thread active. Do not reopen manually collapsed threads during normal polling.

Fourth, pass Codex thread state into `ChartDexVoiceAgent`. Detect status transitions from queued/running to complete/failed and, when connected, inject a system message into the realtime session telling the agent which thread completed and that it can call `get_codex_thread` before briefly notifying the user.

Fifth, update tests for voice tools and Codex panel behavior, then run frontend tests/build and relevant backend tests if shared code changes.

## Validation and Acceptance

Frontend tests must cover:

- Codex voice tools delegate to the adapter.
- Manually collapsed Codex threads remain collapsed during thread refresh.
- A voice focus request opens the requested thread.

Manual acceptance:

- Asking voice to investigate a metric issue creates a new Codex thread and gives a short async acknowledgement.
- When the thread completes while voice is connected, the agent can notify the user briefly and summarize from the actual thread content.

## Idempotence and Recovery

The changes are additive to the voice tool surface. If a tool call fails due to a busy thread or missing thread id, the error should surface through the realtime component’s existing tool error path and browser console logs.

## Artifacts and Notes

Verification commands:

    npm test
    npm --prefix frontend run build
