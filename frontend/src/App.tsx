import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Dashboard, MetricPoint, fetchDashboards, fetchMetric } from "./api";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; dashboards: Dashboard[]; revenue: MetricPoint[] }
  | { status: "error"; message: string };

export function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;

    async function load() {
      const [dashboards, revenue] = await Promise.all([
        fetchDashboards(),
        fetchMetric("revenue"),
      ]);

      if (active) {
        setState({ status: "ready", dashboards, revenue });
      }
    }

    load().catch((error: unknown) => {
      if (active) {
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Unknown error",
        });
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="min-h-screen bg-[#f5f7f8] text-[#172026]">
      <section className="border-b border-[#d7dde1] bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#5c6b60]">
              ChartDex
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal md:text-5xl">
              eCommerce metric exploration
            </h1>
          </div>
          <div className="rounded-md border border-[#cbd7d2] bg-[#f7fbf9] px-4 py-3 text-sm text-[#405048]">
            FastAPI + SQLite backend connected
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[360px_1fr]">
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Org Dashboards</h2>
          {state.status === "loading" ? <p>Loading dashboards...</p> : null}
          {state.status === "error" ? (
            <p className="rounded-md border border-red-300 bg-red-50 p-4 text-red-800">
              {state.message}
            </p>
          ) : null}
          {state.status === "ready"
            ? state.dashboards.map((dashboard) => (
                <article
                  className="rounded-md border border-[#d7dde1] bg-white p-4 shadow-sm"
                  key={dashboard.slug}
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#6c776f]">
                    {dashboard.space} space
                  </p>
                  <h3 className="mt-2 text-base font-semibold">{dashboard.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-[#526058]">
                    {dashboard.description}
                  </p>
                </article>
              ))
            : null}
        </div>

        <div className="rounded-md border border-[#d7dde1] bg-white p-5 shadow-sm">
          <div className="mb-5 flex flex-col gap-1">
            <h2 className="text-lg font-semibold">Revenue Overview</h2>
            <p className="text-sm text-[#526058]">
              Seeded metric data from the separate metrics SQLite database.
            </p>
          </div>
          <div className="h-[360px]">
            {state.status === "ready" ? (
              <ResponsiveContainer height="100%" width="100%">
                <LineChart data={state.revenue}>
                  <CartesianGrid stroke="#e1e7ea" />
                  <XAxis dataKey="observed_on" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Line
                    dataKey="value"
                    dot={{ r: 4 }}
                    name="Revenue"
                    stroke="#23705a"
                    strokeWidth={3}
                    type="monotone"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-[#526058]">
                Waiting for backend data
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
