# ChartDex — Voice + Codex for eCommerce Metric Exploration

## Goal

Build a polished 4-hour hackathon demo app.

ChartDex lets an eCommerce team talk to its metrics. A user can log in, browse shared org dashboards, ask voice/text questions, have Codex explain metrics with diagrams, generate personal dashboards, promote useful dashboards to the org space, and investigate metric anomalies.

The demo should show Codex in two roles:

1. Codex as the engineering partner used to build the app.
2. Codex embedded inside the app as a backend investigator/dashboard author.

The app should satisfy:
- Login / authorization
- Data persistence
- A few meaningful tests
- Programmatic use of Codex inside the app/workflow
- Voice-based interaction using OpenAI realtime voice component where feasible
- Clean open-sourceable code (it likely won't be open sourced, but this is a bar to keep in mind. It should be clean, there should be no embarrassing hacks, no secrets checked in, etc)
- A clean 5-minute demo path

Use the OpenAI realtime voice component for voice control if possible. It supports tool definitions, controller/runtime hooks, a browser WebRTC transport with a server-proxied `/session` bootstrap, and `VoiceControlWidget`. Do not put OpenAI API keys in the browser. Use a backend `/api/realtime/session` endpoint. The Codex SDK can control the local Codex app-server programmatically over JSON-RPC.
