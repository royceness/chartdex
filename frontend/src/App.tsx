import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Dashboard,
  MetricPoint,
  User,
  fetchCurrentUser,
  fetchDashboards,
  fetchMetric,
  login,
  logout,
} from "./api";

type LoadState =
  | { status: "loading" }
  | { status: "login"; message?: string }
  | { status: "ready"; user: User; dashboards: Dashboard[]; revenue: MetricPoint[] }
  | { status: "error"; message: string };

export function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  async function loadAuthenticatedApp(user: User) {
    const [dashboards, revenue] = await Promise.all([
      fetchDashboards(),
      fetchMetric("revenue"),
    ]);
    setState({ status: "ready", user, dashboards, revenue });
  }

  useEffect(() => {
    let active = true;

    async function load() {
      const user = await fetchCurrentUser();
      if (active) {
        await loadAuthenticatedApp(user);
      }
    }

    load().catch((error: unknown) => {
      if (active) {
        const message = error instanceof Error ? error.message : "Unknown error";
        if (error instanceof Error && error.cause === 401) {
          setState({ status: "login" });
          return;
        }
        setState({ status: "error", message });
      }
    });

    return () => {
      active = false;
    };
  }, []);

  async function handleLogin(email: string, password: string) {
    try {
      const user = await login(email, password);
      await loadAuthenticatedApp(user);
    } catch (error) {
      setState({
        status: "login",
        message: error instanceof Error ? "Invalid email or password" : "Login failed",
      });
    }
  }

  async function handleLogout() {
    await logout();
    setState({ status: "login" });
  }

  if (state.status === "login") {
    return <LoginScreen message={state.message} onLogin={handleLogin} />;
  }

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
          {state.status === "ready" ? (
            <div className="flex items-center gap-3">
              <div className="rounded-md border border-[#cbd7d2] bg-[#f7fbf9] px-4 py-3 text-sm text-[#405048]">
                {state.user.name} · {state.user.role}
              </div>
              <button
                className="rounded-md bg-[#172026] px-4 py-3 text-sm font-semibold text-white"
                onClick={handleLogout}
                type="button"
              >
                Log out
              </button>
            </div>
          ) : null}
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
          <div className="h-[360px] min-h-[360px] min-w-0">
            {state.status === "ready" ? (
              <ResponsiveContainer height={360} minWidth={0} width="100%">
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

type LoginScreenProps = {
  message?: string;
  onLogin: (email: string, password: string) => Promise<void>;
};

function LoginScreen({ message, onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState("admin@acme.test");
  const [password, setPassword] = useState("password");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    await onLogin(email, password);
    setIsSubmitting(false);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f7f8] px-6 text-[#172026]">
      <section className="w-full max-w-sm rounded-md border border-[#d7dde1] bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#5c6b60]">
          ChartDex
        </p>
        <h1 className="mt-2 text-2xl font-semibold">Sign in</h1>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium">
            Email
            <input
              className="mt-2 w-full rounded-md border border-[#cbd3d8] px-3 py-2"
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              value={email}
            />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input
              className="mt-2 w-full rounded-md border border-[#cbd3d8] px-3 py-2"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>
          {message ? <p className="text-sm text-red-700">{message}</p> : null}
          <button
            className="w-full rounded-md bg-[#172026] px-4 py-3 text-sm font-semibold text-white disabled:opacity-70"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
