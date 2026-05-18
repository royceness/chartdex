# ChartDex

Voice + Codex for eCommerce metric exploration.

ChartDex is a hackathon demo for an eCommerce analytics team. It combines a
dashboard UI, voice navigation, and backend Codex investigations over seeded
metrics data.

## Development

Install dependencies:

```sh
npm install
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

Configure OpenAI access for voice:

```sh
export OPENAI_API_KEY=sk-...
```

`CHARTDEX_OPENAI_API_KEY` also works. The app never sends this key to the
browser; the FastAPI backend proxies Realtime session creation.

Codex investigations use the local Codex app-server. Make sure `codex` is
installed and logged in:

```sh
codex --version
```

Run the app:

```sh
npm run dev
```

Frontend: http://localhost:5175
Backend: http://localhost:8010

Demo users:

- `admin@acme.test` / `password`
- `analyst@acme.test` / `password`

Run tests:

```sh
npm test
```

## Demo Metrics Data

In demo mode, the backend automatically creates the app database at
`backend/data/app_state.sqlite3` and the metrics database at
`backend/data/metrics.sqlite3` on startup.

To regenerate the Acme Outdoor demo metrics database manually:

```sh
python3 scripts/generate_demo_metrics.py \
  --days 180 \
  --seed 42 \
  --out backend/data/metrics.sqlite3
```

The generated SQLite file is intentionally ignored by git. Commit the generator, context, and tests only. The database includes realistic checkout facts, metric metadata, business events, experiments, UI mappings, seed dashboards, and dashboard-friendly SQL views.

Codex-facing context for the generated dataset lives in `data/metric_context.md`.

## Demo Path

1. Sign in as `admin@acme.test`.
2. Ask voice to show "purchases by platform"; it should navigate to Revenue Overview.
3. Drag-select a dip in Checkout Conversion Over Time.
4. Ask voice: "Can you investigate this?"
5. Open the Codex thread and show the Markdown investigation.
6. Ask voice to "reset my demo" before recording another take.
