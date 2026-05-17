# Generate ChartDex demo metrics data

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document follows the repository-local instruction to use `~/.codex/.agent/PLANS.md` for complex features. The file is not checked into this repository, so the key operational requirement is restated here: keep this plan self-contained, update it as implementation proceeds, and validate the feature with observable commands.

## Purpose / Big Picture

ChartDex needs a deterministic SQLite metrics database that makes the demo feel like a real eCommerce investigation. After this change, a developer can run `python scripts/generate_demo_metrics.py --days 180 --seed 42 --out data/chartdex_demo.sqlite` from the repository root and receive a populated demo database for Acme Outdoor. The generated data includes realistic daily checkout metrics, metadata for ChartDex and Codex, seed dashboards, SQL views, and smoke checks that prove the hidden Android checkout bug is present but subtle at the global level.

## Progress

- [x] (2026-05-18 06:42 +09:30) Created a new worktree at `/Users/royce/.codex/worktrees/chartdex-demo-data/New project 3` on branch `codex/demo-metrics-data`.
- [x] (2026-05-18 06:43 +09:30) Inspected the existing repository layout, backend test conventions, README, and current SQLite usage.
- [x] (2026-05-18 06:44 +09:30) Started this ExecPlan before code changes.
- [x] (2026-05-18 06:45 +09:30) Implemented `scripts/generate_demo_metrics.py` with schema creation, deterministic generation, metadata insertion, views, smoke checks, and CLI arguments.
- [x] (2026-05-18 06:45 +09:30) Added `data/metric_context.md` describing the demo business, metrics, experiments, incidents, hidden generation note, and suggested questions.
- [x] (2026-05-18 06:46 +09:30) Added `tests/test_demo_metrics.py` and updated pytest configuration so root-level tests run with backend tests.
- [x] (2026-05-18 06:46 +09:30) Updated `.gitignore` and `README.md` with demo data generation instructions.
- [x] (2026-05-18 06:46 +09:30) Ran the generator and automated tests, tuned multipliers and low-frequency count rounding, and recorded evidence in this plan.

## Surprises & Discoveries

- Observation: The existing app currently seeds a tiny `metric_points` table in `backend/app/database.py`, but this task is additive.
  Evidence: The new generated metrics database lives at `data/chartdex_demo.sqlite` by default and does not replace the existing API seed path in this milestone.

- Observation: The global hidden-bug dip initially failed because the Frost promo's positive mix outweighed the Android bug.
  Evidence: The first generator run failed with `AssertionError: Global checkout conversion dip should be subtle; dip was -0.74%`. Increasing the affected Android/FROST20 heavy-cart traffic and making the bug more severe produced a final global dip of 2.1%.

- Observation: Rounding low-frequency errors to whole numbers per small slice made ordinary payment error rates unrealistically low and the incident lift unrealistically high.
  Evidence: The generator once printed `Payment incident error lift: 10601.8%`. Switching promo errors, payment errors, and refunds to deterministic stochastic rounding produced `Payment incident error lift: 208.2%`.

- Observation: The local shell has `python3` but not a `python` shim.
  Evidence: Running `python scripts/generate_demo_metrics.py ...` returned `zsh:1: command not found: python`; running the same command with `python3` succeeded.

## Decision Log

- Decision: Use the new sibling worktree `/Users/royce/.codex/worktrees/chartdex-demo-data/New project 3` and branch `codex/demo-metrics-data`.
  Rationale: The user asked for a new work tree, and the original checkout was a detached Codex worktree. A sibling worktree keeps the changes isolated while preserving the original state.
  Date/Author: 2026-05-18 / Codex.

- Decision: Implement the generator as a standard-library Python script rather than integrating it into the FastAPI startup path.
  Rationale: The requested deliverable is a committed generator and context files, not a committed SQLite database or API migration. Keeping generation explicit prevents surprising database rewrites during normal app startup.
  Date/Author: 2026-05-18 / Codex.

- Decision: Store tests under root-level `tests/` and update `pyproject.toml` to include both `backend/tests` and `tests`.
  Rationale: The requested deliverable names `tests/test_demo_metrics.py`, while existing backend tests live under `backend/tests`. Pytest can run both without changing existing test imports.
  Date/Author: 2026-05-18 / Codex.

- Decision: Use deterministic stochastic rounding for low-frequency metrics such as promo errors, payment errors, and refunds.
  Rationale: Fact rows are small aggregate slices. Plain integer rounding suppressed baseline errors, which made incidents look implausibly large. Stochastic rounding keeps the generator deterministic through the seed while preserving realistic aggregate rates.
  Date/Author: 2026-05-18 / Codex.

## Outcomes & Retrospective

Implemented the requested demo data generator, metric context file, SQL schema and views, metadata seed rows, dashboard seed rows, and smoke tests. The generator creates `data/chartdex_demo.sqlite` locally and `.gitignore` prevents committing it. The final default run produced 77,636 fact rows for 2025-11-20 through 2026-05-18 with a 2.1% global checkout conversion dip, a 19.8% Android checkout_v2 treatment dip, and a 67.4% conversion drop in the hidden Android/FROST20/3+ heavy-cart slice. Backend and demo data tests pass in the repo venv, and frontend tests pass after installing npm dependencies.

## Context and Orientation

The repository is a small ChartDex scaffold. `backend/app/database.py` creates two SQLite databases for application state and a small metrics seed when the FastAPI app starts. `backend/tests/test_api.py` validates the existing health, auth, dashboard, and metric endpoints. `README.md` contains development setup and test commands. `pyproject.toml` configures pytest to look only in `backend/tests` today.

The new generator will create a separate demo metrics database at `data/chartdex_demo.sqlite` by default. A fact table is a table of already-aggregated metrics, not raw user events. Each row in `metric_facts_daily` represents a daily metric slice for one combination of dimensions such as platform, channel, promo code, checkout variant, cart size, and cart weight. The script will also create metadata tables that explain metrics and dashboards to ChartDex and Codex.

The hidden bug is an intentionally generated anomaly for demo investigation. It affects only Android app users in the `checkout_v2_treatment` variant who use promo code `FROST20` with 3+ heavy carts near the end of the dataset. It should create obvious promo and payment error increases in that narrow slice while leaving global conversion only slightly lower.

## Plan of Work

First, create `scripts/generate_demo_metrics.py`. The script will parse `--days`, `--seed`, `--start-date`, `--end-date`, and `--out`. It will derive a date range, create the output directory, replace any existing output database at the requested path, create schema tables, insert metadata rows, generate daily fact rows, create views, run smoke checks, and print a concise summary. Generation will use only `argparse`, `datetime`, `json`, `math`, `random`, `sqlite3`, and `pathlib`.

The generation model will iterate dates and produce a fixed number of weighted daily slices, plus guaranteed slices for the hidden bug dimensions. Weighted random choices allocate traffic across platform, channel, region, segment, product category, cart size, cart weight, promo code, and checkout variant. The funnel is generated by applying deterministic rates with trend, weekday, promotions, experiments, incidents, and bug modifiers. Counts are rounded to integers and constrained so downstream funnel counts do not exceed upstream counts.

Second, add `data/metric_context.md`. This file will explain Acme Outdoor, the checkout funnel, key formulas, dimensions, event timeline, hidden data-generation note marked as not known to the app user, and suggested demo questions. The generated SQLite database itself will not be committed.

Third, add `tests/test_demo_metrics.py`. The tests will import the generator module from `scripts/generate_demo_metrics.py`, generate a temporary 180-day database with seed 42, and assert the schema, metadata, views, deterministic smoke checks, and hidden-bug properties. The tests will avoid committing or depending on `data/chartdex_demo.sqlite`.

Fourth, update `.gitignore` so generated SQLite files under `data/` are ignored, and update `README.md` with the exact command to generate the demo database and run tests.

## Concrete Steps

From `/Users/royce/.codex/worktrees/chartdex-demo-data/New project 3`, run:

    python scripts/generate_demo_metrics.py --days 180 --seed 42 --out data/chartdex_demo.sqlite

Expected result: the command prints a summary including row count, date range, hidden bug conversion drop, global conversion dip, and smoke-check success. It creates `data/chartdex_demo.sqlite`, which is ignored by git.

Observed result on 2026-05-18:

    Generated ChartDex demo metrics database: data/chartdex_demo.sqlite
    Seed: 42
    Date range: 2025-11-20 to 2026-05-18 (180 days)
    Fact rows: 77,636
    Revenue spread: 132.7%
    Weekend session lift: 12.0%
    Payment incident error lift: 208.2%
    checkout_v2 treatment lift before hidden bug: 8.2%
    Hidden bug slice checkout conversion drop: 67.4%
    Hidden bug promo error lift: 531.4%
    Hidden bug payment error lift: 181.7%
    Global checkout conversion dip: 2.1%
    Android checkout_v2 treatment dip: 19.8%
    iOS checkout_v2 treatment change: -1.0%
    Smoke checks passed.

Run tests from the same directory:

    pytest

Expected result: the existing backend tests and the new demo metrics tests pass.

Observed result in `.venv` on 2026-05-18:

    14 passed in 5.32s

Observed frontend test result after `npm install && npm --prefix frontend install`:

    Test Files  1 passed (1)
    Tests  3 passed (3)

## Validation and Acceptance

Acceptance is met when `python scripts/generate_demo_metrics.py --days 180 --seed 42 --out data/chartdex_demo.sqlite` creates a database with the required tables and views, prints successful smoke checks, and does not leave the SQLite database tracked by git. Acceptance is also met when `pytest` passes, including assertions that the row count is greater than 20,000, the hidden bug slice has a conversion drop of at least 40%, promo error rate increase of at least 200%, payment error rate increase of at least 100%, the global conversion dip is only 1-5%, Android checkout_v2 treatment has a visible dip, and iOS checkout_v2 treatment remains mostly stable.

## Idempotence and Recovery

The generator will replace the requested output database path atomically enough for local development: if the target file exists, it is unlinked before creating a fresh SQLite file. Re-running with the same seed and date range should produce identical data. If generation or checks fail, delete the output file and rerun the same command after tuning the generator. The committed files are additive except for README, `.gitignore`, and pytest configuration updates.

## Artifacts and Notes

Evidence will be recorded here after implementation. The most important transcript will be the generator summary and pytest result.
The committed artifacts are `scripts/generate_demo_metrics.py`, `data/metric_context.md`, `tests/test_demo_metrics.py`, and this plan. Existing files updated are `.gitignore`, `README.md`, and `pyproject.toml`.

`git check-ignore -v data/chartdex_demo.sqlite` confirms the generated database is ignored:

    .gitignore:15:data/*.sqlite data/chartdex_demo.sqlite

## Interfaces and Dependencies

In `scripts/generate_demo_metrics.py`, define a public function:

    def generate_database(out_path: Path, *, days: int, seed: int, start_date: date | None = None, end_date: date | None = None) -> dict[str, object]:

The function returns a summary dictionary produced after smoke checks. Tests can call this function directly. The module will also define `main()` for CLI usage.

No third-party dependencies are required for the generator.

## Debt and future issues

No future issues have been identified yet.
