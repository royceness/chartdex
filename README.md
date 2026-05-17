# ChartDex

Voice + Codex for eCommerce metric exploration.

## Development

Install dependencies:

```sh
npm install
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

Run the app:

```sh
npm run dev
```

Frontend: http://localhost:5175
Backend: http://localhost:8010

Run tests:

```sh
npm test
. .venv/bin/activate && pytest
```

## Demo Metrics Data

Generate the Acme Outdoor demo metrics database:

```sh
python scripts/generate_demo_metrics.py \
  --days 180 \
  --seed 42 \
  --out data/chartdex_demo.sqlite
```

If your environment does not provide `python`, use `python3`.

The generated SQLite file is intentionally ignored by git. Commit the generator, context, and tests only. The database includes realistic checkout facts, metric metadata, business events, experiments, UI mappings, seed dashboards, and dashboard-friendly SQL views.

Codex-facing context for the generated dataset lives in `data/metric_context.md`.
