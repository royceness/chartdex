import { Children, isValidElement, useEffect, useState } from "react";
import type { FormEvent, ReactElement, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CategoryPoint,
  CodexThread,
  Dashboard,
  DashboardDetail,
  DashboardPanel,
  MetricPoint,
  User,
  fetchCodexThreads,
  fetchCurrentUser,
  fetchDashboardDetail,
  fetchDashboards,
  login,
  logout,
} from "./api";

type ChartSelection = {
  dashboardId: string;
  panelId: string;
  metricKey: string;
  rangeStart: string;
  rangeEnd: string;
};

type LoadState =
  | { status: "loading" }
  | { status: "login"; message?: string }
  | {
      status: "ready";
      user: User;
      dashboards: Dashboard[];
      selectedDashboard: DashboardDetail;
      threads: CodexThread[];
    }
  | { status: "error"; message: string };

export function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<ChartSelection | null>(null);

  async function loadAuthenticatedApp(user: User, dashboardId?: string) {
    const dashboards = await fetchDashboards();
    const selectedId =
      dashboardId ?? dashboards.find((dashboard) => dashboard.slug === "checkout-funnel")?.id ?? dashboards[0]?.id;
    if (!selectedId) {
      throw new Error("No dashboards available");
    }

    const [selectedDashboard, threads] = await Promise.all([
      fetchDashboardDetail(selectedId),
      fetchCodexThreads(),
    ]);
    setState({ status: "ready", user, dashboards, selectedDashboard, threads });
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
      if (!active) {
        return;
      }
      if (error instanceof Error && error.cause === 401) {
        setState({ status: "login" });
        return;
      }
      setState({ status: "error", message: error instanceof Error ? error.message : "Unknown error" });
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

  async function handleSelectDashboard(dashboardId: string) {
    if (state.status !== "ready" || dashboardId === state.selectedDashboard.id) {
      return;
    }
    setSelection(null);
    const selectedDashboard = await fetchDashboardDetail(dashboardId);
    setState({ ...state, selectedDashboard });
  }

  async function handleLogout() {
    await logout();
    setSelection(null);
    setState({ status: "login" });
  }

  if (state.status === "login") {
    return <LoginScreen message={state.message} onLogin={handleLogin} />;
  }

  if (state.status === "loading") {
    return <LoadingScreen />;
  }

  if (state.status === "error") {
    return <ErrorScreen message={state.message} />;
  }

  return (
    <DashboardShell
      dashboards={state.dashboards}
      onLogout={handleLogout}
      onSelectDashboard={handleSelectDashboard}
      onSelectRange={setSelection}
      selectedDashboard={state.selectedDashboard}
      selection={selection}
      threads={state.threads}
      user={state.user}
    />
  );
}

function DashboardShell({
  dashboards,
  onLogout,
  onSelectDashboard,
  onSelectRange,
  selectedDashboard,
  selection,
  threads,
  user,
}: {
  dashboards: Dashboard[];
  onLogout: () => Promise<void>;
  onSelectDashboard: (dashboardId: string) => Promise<void>;
  onSelectRange: (selection: ChartSelection | null) => void;
  selectedDashboard: DashboardDetail;
  selection: ChartSelection | null;
  threads: CodexThread[];
  user: User;
}) {
  const orgDashboards = dashboards.filter((dashboard) => dashboard.space === "org");
  const personalDashboards = dashboards.filter((dashboard) => dashboard.space === "personal");

  return (
    <main className="grid h-screen overflow-hidden grid-cols-[280px_minmax(520px,1fr)_392px] bg-[#050912] text-slate-100">
      <DashboardSidebar
        onLogout={onLogout}
        onSelectDashboard={onSelectDashboard}
        orgDashboards={orgDashboards}
        personalDashboards={personalDashboards}
        selectedDashboardId={selectedDashboard.id}
      />
      <section className="flex h-screen min-h-0 flex-col overflow-hidden border-x border-slate-800 bg-[#090e18]">
        <header className="z-10 flex min-h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-[#090e18]/95 px-8 backdrop-blur">
          <input
            aria-label="Ask a question"
            className="h-10 w-full max-w-2xl rounded-md border border-slate-700 bg-slate-950/80 px-4 text-sm text-slate-100 outline-none ring-blue-500/20 placeholder:text-slate-500 focus:ring-4"
            placeholder="Ask a question"
          />
          <div className="ml-4 rounded-full border border-blue-400/50 bg-blue-500/20 px-3 py-2 text-sm text-blue-100">
            Voice
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">
          <DashboardCanvas
            dashboard={selectedDashboard}
            onSelectRange={onSelectRange}
            selection={selection}
          />
        </div>
      </section>
      <CodexPanel threads={threads} />
    </main>
  );
}

function DashboardSidebar({
  onLogout,
  onSelectDashboard,
  orgDashboards,
  personalDashboards,
  selectedDashboardId,
}: {
  onLogout: () => Promise<void>;
  onSelectDashboard: (dashboardId: string) => Promise<void>;
  orgDashboards: Dashboard[];
  personalDashboards: Dashboard[];
  selectedDashboardId: string;
}) {
  return (
    <aside className="flex h-screen min-h-0 flex-col overflow-hidden bg-[#060b14]">
      <div className="flex h-16 shrink-0 items-center gap-3 border-b border-slate-800 px-6">
        <div className="flex h-7 w-8 items-end gap-1">
          <span className="h-3 w-1.5 rounded bg-blue-400" />
          <span className="h-5 w-1.5 rounded bg-indigo-400" />
          <span className="h-7 w-1.5 rounded bg-violet-400" />
        </div>
        <div className="text-xl font-semibold">ChartDex</div>
      </div>

      <nav className="min-h-0 flex-1 overflow-auto px-4 py-6">
        <DashboardNavGroup
          dashboards={orgDashboards}
          label="Org Dashboards"
          onSelectDashboard={onSelectDashboard}
          selectedDashboardId={selectedDashboardId}
        />
        <div className="my-6 border-t border-slate-800" />
        <DashboardNavGroup
          dashboards={personalDashboards}
          label="My Dashboards"
          onSelectDashboard={onSelectDashboard}
          selectedDashboardId={selectedDashboardId}
        />
      </nav>

      <div className="shrink-0 space-y-2 border-t border-slate-800 bg-[#060b14] p-4">
        <button className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-900" type="button">
          Settings
        </button>
        <button
          className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-900"
          onClick={() => void onLogout()}
          type="button"
        >
          Log out
        </button>
      </div>
    </aside>
  );
}

function DashboardNavGroup({
  dashboards,
  label,
  onSelectDashboard,
  selectedDashboardId,
}: {
  dashboards: Dashboard[];
  label: string;
  onSelectDashboard: (dashboardId: string) => Promise<void>;
  selectedDashboardId: string;
}) {
  return (
    <section>
      <h2 className="mb-3 px-2 text-sm font-semibold text-slate-300">{label}</h2>
      <div className="space-y-1">
        {dashboards.map((dashboard) => (
          <button
            className={
              dashboard.id === selectedDashboardId
                ? "flex w-full items-center gap-3 rounded-md border border-blue-400/30 bg-blue-500/30 px-3 py-2.5 text-left text-sm font-medium text-white"
                : "flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-900"
            }
            key={dashboard.id}
            onClick={() => void onSelectDashboard(dashboard.id)}
            type="button"
          >
            <span className="text-slate-400">{dashboard.space === "org" ? "▥" : "⌁"}</span>
            <span className="truncate">{dashboard.name}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function DashboardCanvas({
  dashboard,
  onSelectRange,
  selection,
}: {
  dashboard: DashboardDetail;
  onSelectRange: (selection: ChartSelection | null) => void;
  selection: ChartSelection | null;
}) {
  return (
    <div className="mx-auto max-w-5xl px-8 py-7">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">{dashboard.name}</h1>
          <p className="mt-2 text-sm text-slate-400">{dashboard.description}</p>
          {selection ? (
            <p className="mt-3 rounded-md border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-100">
              Selected {selection.metricKey} from {selection.rangeStart} to {selection.rangeEnd}
            </p>
          ) : null}
        </div>
        <button className="shrink-0 rounded-md border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-200" type="button">
          {dashboard.time_range_label}
        </button>
      </div>

      <div className="space-y-4">
        {dashboard.panels.map((panel) => (
          <DashboardPanelCard
            dashboardId={dashboard.id}
            key={panel.id}
            onSelectRange={onSelectRange}
            panel={panel}
            selection={selection}
          />
        ))}
        <button
          className="flex h-12 w-full items-center justify-center rounded-md border border-dashed border-slate-700 text-sm text-slate-500 hover:border-blue-500/50 hover:text-blue-200"
          type="button"
        >
          + Add panel
        </button>
      </div>
    </div>
  );
}

function DashboardPanelCard({
  dashboardId,
  onSelectRange,
  panel,
  selection,
}: {
  dashboardId: string;
  onSelectRange: (selection: ChartSelection | null) => void;
  panel: DashboardPanel;
  selection: ChartSelection | null;
}) {
  return (
    <article className="rounded-md border border-slate-800 bg-slate-900/70 p-4 shadow-xl shadow-black/20">
      <h2 className="mb-3 text-sm font-semibold text-white">{panel.title}</h2>
      {panel.type === "line" ? (
        <InteractiveLinePanel
          dashboardId={dashboardId}
          onSelectRange={onSelectRange}
          panel={panel}
          selection={selection?.panelId === panel.id ? selection : null}
        />
      ) : null}
      {panel.type === "bar" ? <BarPanel data={panel.data} valueFormat={panel.value_format} /> : null}
      {panel.type === "funnel" ? <FunnelPanel data={panel.data} /> : null}
    </article>
  );
}

function InteractiveLinePanel({
  dashboardId,
  onSelectRange,
  panel,
  selection,
}: {
  dashboardId: string;
  onSelectRange: (selection: ChartSelection | null) => void;
  panel: Extract<DashboardPanel, { type: "line" }>;
  selection: ChartSelection | null;
}) {
  const [dragStart, setDragStart] = useState<string | null>(null);
  const [dragEnd, setDragEnd] = useState<string | null>(null);
  const referenceRange = normalizeRange(dragStart, dragEnd) ?? (selection ? [selection.rangeStart, selection.rangeEnd] : null);

  return (
    <div className="h-40 min-w-0">
      <ResponsiveContainer height={160} minWidth={0} width="100%">
        <LineChart
          data={panel.data}
          onMouseDown={(event) => {
            if (typeof event.activeLabel === "string") {
              setDragStart(event.activeLabel);
              setDragEnd(event.activeLabel);
            }
          }}
          onMouseMove={(event) => {
            if (dragStart && typeof event.activeLabel === "string") {
              setDragEnd(event.activeLabel);
            }
          }}
          onMouseUp={() => {
            const range = normalizeRange(dragStart, dragEnd);
            if (range) {
              onSelectRange({
                dashboardId,
                panelId: panel.id,
                metricKey: panel.metric_key,
                rangeStart: range[0],
                rangeEnd: range[1],
              });
            }
            setDragStart(null);
            setDragEnd(null);
          }}
        >
          <CartesianGrid stroke="#253044" strokeDasharray="4 4" />
          <XAxis dataKey="observed_on" tick={{ fill: "#94a3b8", fontSize: 12 }} />
          <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} tickFormatter={(value) => formatAxisValue(value, panel.value_format)} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6 }} formatter={(value) => formatValue(Number(value), panel.value_format)} />
          {referenceRange ? <ReferenceArea fill="#3b82f6" fillOpacity={0.18} x1={referenceRange[0]} x2={referenceRange[1]} /> : null}
          <Line dataKey="value" dot={false} name={panel.title} stroke={panel.metric_key === "conversion" ? "#a855f7" : "#3b82f6"} strokeWidth={3} type="monotone" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function BarPanel({ data, valueFormat }: { data: CategoryPoint[]; valueFormat: DashboardPanel["value_format"] }) {
  return (
    <div className="h-36 min-w-0">
      <ResponsiveContainer height={144} minWidth={0} width="100%">
        <BarChart data={data}>
          <CartesianGrid stroke="#253044" strokeDasharray="4 4" />
          <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 12 }} />
          <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} tickFormatter={(value) => formatAxisValue(value, valueFormat)} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6 }} formatter={(value) => formatValue(Number(value), valueFormat)} />
          <Bar dataKey="value" fill="#22c55e" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function FunnelPanel({ data }: { data: CategoryPoint[] }) {
  return (
    <div className="grid grid-cols-5 overflow-hidden rounded-md border border-slate-800">
      {data.map((step, index) => (
        <div
          className="min-h-24 border-r border-slate-800 bg-gradient-to-br from-blue-700 to-emerald-500 p-3 text-center last:border-r-0"
          key={step.label}
          style={{ opacity: 0.62 + index * 0.08 }}
        >
          <div className="text-xs text-white/90">{step.label}</div>
          <div className="mt-2 text-sm font-semibold text-white">{formatInteger(step.value)}</div>
          {step.rate ? <div className="mt-1 text-xs text-white/80">{step.rate}%</div> : null}
        </div>
      ))}
    </div>
  );
}

function CodexPanel({ threads }: { threads: CodexThread[] }) {
  const [openThreadIds, setOpenThreadIds] = useState<Set<string>>(() => new Set(threads.slice(0, 3).map((thread) => thread.id)));
  const [activeThreadId, setActiveThreadId] = useState(threads[0]?.id ?? null);

  useEffect(() => {
    setOpenThreadIds(new Set(threads.slice(0, 3).map((thread) => thread.id)));
    setActiveThreadId(threads[0]?.id ?? null);
  }, [threads]);

  return (
    <aside className="flex h-screen min-h-0 flex-col overflow-hidden bg-[#060b14]">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 px-5">
        <div className="text-sm font-semibold text-white">✦ Codex</div>
        <button className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200" type="button">
          + New thread
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto space-y-3 p-4">
        {threads.map((thread, index) => {
          const isOpen = openThreadIds.has(thread.id);
          const isActive = activeThreadId === thread.id;
          return (
            <article
              className={isActive ? "overflow-hidden rounded-md border border-blue-500/50 bg-slate-950" : "overflow-hidden rounded-md border border-slate-800 bg-slate-950"}
              key={thread.id}
            >
              <button
                aria-expanded={isOpen}
                className="flex w-full items-center justify-between gap-3 p-4 text-left hover:bg-slate-900"
                onClick={() => {
                  setActiveThreadId(thread.id);
                  setOpenThreadIds((current) => {
                    const next = new Set(current);
                    if (next.has(thread.id)) {
                      next.delete(thread.id);
                    } else {
                      next.add(thread.id);
                    }
                    return next;
                  });
                }}
                type="button"
              >
                <span className="text-sm text-slate-400">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold text-white">{thread.title}</span>
                <span className={statusClass(thread.status)}>{thread.status}</span>
                <span className="text-slate-400">{isOpen ? "⌃" : "⌄"}</span>
              </button>
              {isOpen ? <ThreadBody thread={thread} /> : null}
            </article>
          );
        })}
      </div>
    </aside>
  );
}

function ThreadBody({ thread }: { thread: CodexThread }) {
  const [utterance, setUtterance] = useState("");
  return (
    <div className="space-y-4 border-t border-slate-800 p-4">
      {thread.turns.length === 0 ? <p className="text-sm text-slate-500">Waiting to start.</p> : null}
      {thread.turns.map((turn) => (
        <div className={turn.role === "user" ? "rounded-md bg-slate-900 p-3" : "rounded-md bg-blue-500/5 p-3"} key={turn.id}>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{turn.role}</div>
          <MarkdownContent markdown={turn.markdown} />
        </div>
      ))}
      <form
        className="flex gap-2 border-t border-slate-800 pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          setUtterance("");
        }}
      >
        <input
          className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600"
          onChange={(event) => setUtterance(event.target.value)}
          placeholder="Ask a follow-up..."
          value={utterance}
        />
        <button className="rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!utterance.trim()} type="submit">
          Send
        </button>
      </form>
    </div>
  );
}

function MarkdownContent({ markdown }: { markdown: string }) {
  return (
    <div className="markdown-body text-sm leading-6 text-slate-300">
      <ReactMarkdown
        components={{
          pre({ children }) {
            const child = Children.only(children) as ReactElement<{ children?: ReactNode; className?: string }>;
            if (isValidElement(child)) {
              const language = /language-(\w+)/.exec(child.props.className ?? "")?.[1];
              if (language === "mermaid") {
                return <MermaidPlaceholder source={String(child.props.children).replace(/\n$/, "")} />;
              }
            }
            return <pre>{children}</pre>;
          },
          code({ children, className }) {
            return <code className={className}>{children}</code>;
          },
        }}
        remarkPlugins={[remarkGfm]}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function MermaidPlaceholder({ source }: { source: string }) {
  return (
    <div className="my-3 rounded-md border border-blue-500/30 bg-blue-500/10 p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-blue-200">Mermaid diagram</div>
      <pre className="overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">{source}</pre>
    </div>
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
    <main className="flex min-h-screen items-center justify-center bg-[#050912] px-6 text-slate-100">
      <section className="w-full max-w-sm rounded-md border border-slate-800 bg-slate-950 p-6 shadow-xl shadow-black/30">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-blue-300">ChartDex</p>
        <h1 className="mt-2 text-2xl font-semibold">Sign in</h1>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium">
            Email
            <input className="mt-2 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" onChange={(event) => setEmail(event.target.value)} type="email" value={email} />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input className="mt-2 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
          </label>
          {message ? <p className="text-sm text-red-300">{message}</p> : null}
          <button className="w-full rounded-md bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-70" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function LoadingScreen() {
  return <main className="flex min-h-screen items-center justify-center bg-[#050912] text-sm text-slate-400">Loading ChartDex...</main>;
}

function ErrorScreen({ message }: { message: string }) {
  return <main className="flex min-h-screen items-center justify-center bg-[#050912] p-6 text-sm text-red-200">{message}</main>;
}

function normalizeRange(start: string | null, end: string | null): [string, string] | null {
  if (!start || !end) {
    return null;
  }
  return start <= end ? [start, end] : [end, start];
}

function formatAxisValue(value: number | string, format: DashboardPanel["value_format"]) {
  const numeric = Number(value);
  if (format === "currency") {
    return `$${(numeric / 1_000_000).toFixed(1)}M`;
  }
  if (format === "percent") {
    return `${numeric}%`;
  }
  return formatInteger(numeric);
}

function formatValue(value: number, format: DashboardPanel["value_format"]) {
  if (format === "currency") {
    return new Intl.NumberFormat("en-US", { currency: "USD", maximumFractionDigits: 0, style: "currency" }).format(value);
  }
  if (format === "percent") {
    return `${value.toFixed(1)}%`;
  }
  return formatInteger(value);
}

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function statusClass(status: CodexThread["status"]) {
  const base = "rounded px-2 py-1 text-xs";
  if (status === "complete") {
    return `${base} bg-emerald-500/10 text-emerald-300`;
  }
  if (status === "failed") {
    return `${base} bg-red-500/10 text-red-300`;
  }
  if (status === "running") {
    return `${base} bg-blue-500/10 text-blue-300`;
  }
  return `${base} bg-amber-500/10 text-amber-300`;
}
