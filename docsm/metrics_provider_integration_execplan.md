# Org-Scoped Metrics Provider Integration

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows the ExecPlan guidance in `/Users/royce/.codex/.agent/PLANS.md`. This document is self-contained so a future contributor can understand the metrics-provider integration without conversation history.

## Purpose / Big Picture

After this change, ChartDex no longer serves dashboard chart data from tiny hardcoded mock metric arrays. The backend will use a metrics provider boundary: the authenticated user's `org_id` resolves to an internal provider configuration, and the provider serves dashboard panel data from that organization's generated SQLite metrics database. The frontend should keep working with the same dashboard-shell response shape, but the data behind the panels will come from realistic generated eCommerce facts and views.

## Progress

- [x] (2026-05-17 21:59Z) Merged branch `codex/demo-metrics-data` into `main`.
- [x] (2026-05-17 22:00Z) Reviewed generated metrics schema, seed dashboard table, views, and tests.
- [x] (2026-05-17 22:06Z) Added app-state storage for org metrics provider configuration.
- [x] (2026-05-17 22:06Z) Added a metrics provider interface and SQLite provider implementation.
- [x] (2026-05-17 22:06Z) Generate or verify the demo metrics SQLite file during demo startup.
- [x] (2026-05-17 22:07Z) Replaced mock panel data in dashboard detail with provider-backed panel data.
- [x] (2026-05-17 22:07Z) Kept API authorization deriving org access only from `AuthContext`, never from client-provided org IDs or file paths.
- [x] (2026-05-17 22:08Z) Updated tests for provider binding and dashboard data backed by generated metrics.
- [x] (2026-05-17 22:09Z) Ran backend tests, frontend tests, frontend build, and browser verification.

## Surprises & Discoveries

- Observation: The merged generator creates an organization-agnostic metrics SQLite file.
  Evidence: `scripts/generate_demo_metrics.py` creates `metric_facts_daily` without an `org_id` column, and the generated dashboard metadata lives in `seed_dashboards`.

- Observation: This organization-agnostic file still fits the authorization requirement if the app binds one metrics database file to one org internally.
  Evidence: The backend already authenticates users into an `AuthContext` containing `org_id`; app state can map that `org_id` to a provider type and database path.

- Observation: The old `/api/dashboards` route was returning all personal dashboards in the org.
  Evidence: While wiring the provider, the route used `list_dashboards(..., org_id=auth.org_id)` without `space` or `owner_user_id`. It now returns org dashboards plus only personal dashboards where `owner_user_id == auth.user_id`.

## Decision Log

- Decision: Treat the metrics SQLite file as org-bound rather than row-scoped.
  Rationale: The user approved this direction. It keeps the generated metrics schema clean and mirrors a future Databricks-style provider, where access is controlled by backend-owned configuration rather than client-supplied filters.
  Date/Author: 2026-05-17 / Codex

- Decision: Add a `MetricsProvider` protocol and a `SQLiteMetricsProvider` implementation.
  Rationale: The rest of the app should ask for dashboard summaries and panel data through a stable backend interface. A future Databricks, warehouse, or metrics-service provider can implement the same methods without rewriting route authorization or frontend code.
  Date/Author: 2026-05-17 / Codex

- Decision: Keep dashboard detail as one response containing panel data for now.
  Rationale: The current frontend shell already consumes this shape. The provider implementation keeps panel SQL behind allowlisted backend methods, so splitting panel data into separate endpoints later will not require changing authorization or data-source ownership.
  Date/Author: 2026-05-17 / Codex

## Outcomes & Retrospective

Implemented and validated. The app now stores internal org metrics provider configuration in `org_metric_providers`, binds `org_acme` to a SQLite metrics database, generates the deterministic demo metrics database when missing in demo mode, and serves dashboard panel data through `SQLiteMetricsProvider`. `/api/dashboards` now returns org dashboards plus only the current user's personal dashboards. Dashboard detail data comes from generated metrics views and facts rather than mock arrays. Future work remains to add Databricks or other provider implementations and to persist Codex-created personal dashboards.

## Context and Orientation

The backend lives under `backend/app`. Authentication is implemented in `backend/app/auth.py`; routes in `backend/app/main.py` use `AuthContext` from `require_auth`. App-state SQLite setup and dashboard seed data currently live in `backend/app/database.py`. The frontend shell calls `GET /api/dashboards`, `GET /api/dashboards/{dashboard_id}`, and `GET /api/codex/threads`.

The merged metrics generator lives in `scripts/generate_demo_metrics.py`. It creates `data/chartdex_demo.sqlite` by default. That generated database includes fact table `metric_facts_daily`, dashboard metadata table `seed_dashboards`, metric metadata table `metric_catalog`, and views such as `v_daily_overview`, `v_checkout_by_platform`, `v_promo_performance`, and `v_experiment_rollout`.

## Plan of Work

First, extend the app-state schema with a provider configuration table. For this demo, the table should map `org_acme` to provider type `sqlite` and the configured metrics database path. This table is internal; no API accepts provider config from the browser.

Second, add `backend/app/metrics_provider.py`. Define a `MetricsProvider` protocol with methods for dashboard summaries, dashboard detail, and legacy metric points. Add `SQLiteMetricsProvider`, which opens the configured database path and executes allowlisted SQL queries. Add a resolver function that takes `app_db_path` and `org_id`, reads the provider config, and returns the provider. If no provider is configured, fail visibly.

Third, update demo startup in `backend/app/database.py` to generate `data/chartdex_demo.sqlite` if demo mode is enabled and the configured metrics database is missing. Use `scripts.generate_demo_metrics.generate_database` with the deterministic default seed, days, and end date. Bind that file to `org_acme` in app state.

Fourth, use `seed_dashboards` from the metrics database to seed org dashboards into app state. Personal dashboards can remain demo app-state rows for now. Dashboard detail should get app-state authorization first, then call the metrics provider to build panels using real metrics queries.

Fifth, update tests to verify protected access, provider configuration, generated panel data, and hidden-bug discoverability through the provider. The frontend should not need a major API shape change.

## Concrete Steps

Run all commands from `/Users/royce/Documents/New project 3`.

Validate the merged generator and backend integration:

    . .venv/bin/activate && pytest

Validate the frontend:

    npm test
    npm --prefix frontend run build

Run the app:

    npm run dev

Open `http://127.0.0.1:5175/`, sign in as `admin@acme.test` with password `password`, and verify the dashboard shell still renders but now uses generated metrics data.

## Validation and Acceptance

Acceptance is met when protected dashboard endpoints derive the user's org from the JWT, resolve that org to an internal metrics provider, and return dashboard panel data from the generated SQLite metrics database. Tests must prove unauthenticated callers are rejected, authenticated callers receive generated dashboard data, the generated demo metrics tests still pass, and the frontend shell still builds and renders.

## Idempotence and Recovery

The generator is deterministic and replaces its output file when called directly. Startup generation should only create the demo metrics file if it is missing, so ordinary server starts do not rewrite data unexpectedly. If local state becomes confusing, delete `backend/data` and `data/chartdex_demo.sqlite`, then restart `npm run dev`.

## Artifacts and Notes

The provider boundary should ensure no route accepts a metrics database path or org id from the browser. The only authorization input is the HttpOnly-cookie JWT, decoded into `AuthContext`.

## Interfaces and Dependencies

In `backend/app/metrics_provider.py`, define:

    class MetricsProvider(Protocol):
        def list_seed_dashboards(self) -> list[dict[str, object]]: ...
        def get_dashboard_detail(self, dashboard: dict[str, object]) -> dict[str, object]: ...
        def list_metric_points(self, metric: str) -> list[dict[str, object]]: ...

Add:

    class SQLiteMetricsProvider:
        def __init__(self, db_path: Path) -> None: ...

Add provider resolver:

    def get_metrics_provider_for_org(app_db_path: Path, org_id: str) -> MetricsProvider: ...

## Debt and Future Issues

Real personal dashboard persistence is still out of scope. Codex thread persistence and real Codex app-server integration remain future work. The provider interface should make those easier by keeping metrics access behind one backend-owned boundary.

Revision note, 2026-05-17: Initial ExecPlan created after merging the demo metrics branch and before provider implementation.

Revision note, 2026-05-17: Updated progress, discoveries, decisions, and outcomes after implementing the SQLite metrics provider integration.
