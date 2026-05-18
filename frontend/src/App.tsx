import { Children, isValidElement, useCallback, useEffect, useRef, useState } from "react";
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
  CodexThreadContext,
  Dashboard,
  DashboardDetail,
  DashboardPanel,
  MetricPoint,
  User,
  appendCodexThreadTurn,
  createCodexThread,
  fetchCodexThreads,
  fetchCurrentUser,
  fetchDashboardDetail,
  fetchDashboards,
  login,
  logout,
  resetDemo,
} from "./api";
import { ChartDexVoiceAgent } from "./voice/ChartDexVoiceAgent";

type ChartSelection = {
  dashboardId: string;
  panelId: string;
  metricKey: string;
  rangeStart: string;
  rangeEnd: string;
};

type CodexThreadFocusRequest = {
  requestId: number;
  threadId: string;
};

type LoadState =
  | { status: "loading" }
  | { status: "login"; message?: string }
  | {
      status: "ready";
      user: User;
      dashboards: Dashboard[];
      dashboardDetails: Record<string, DashboardDetail>;
      selectedDashboard: DashboardDetail;
      threads: CodexThread[];
    }
  | { status: "error"; message: string };

export function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<ChartSelection | null>(null);
  const [focusedPanelId, setFocusedPanelId] = useState<string | null>(null);

  async function loadAuthenticatedApp(user: User, dashboardId?: string) {
    const dashboardState = await loadDashboardState(dashboardId);
    const threads = await fetchCodexThreads();
    setState({ status: "ready", user, ...dashboardState, threads });
  }

  async function loadDashboardState(dashboardId?: string) {
    const dashboards = await fetchDashboards();
    const selectedId =
      dashboardId ?? dashboards.find((dashboard) => dashboard.slug === "checkout-funnel")?.id ?? dashboards[0]?.id;
    if (!selectedId) {
      throw new Error("No dashboards available");
    }

    const dashboardDetailEntries = await Promise.all(
      dashboards.map(async (dashboard) => [dashboard.id, await fetchDashboardDetail(dashboard.id)] as const),
    );
    const dashboardDetails = Object.fromEntries(dashboardDetailEntries);
    const fallbackId = dashboards[0]?.id;
    const selectedDashboard = dashboardDetails[selectedId] ?? (fallbackId ? dashboardDetails[fallbackId] : undefined);
    if (!selectedDashboard) {
      throw new Error(`Dashboard detail not found for ${selectedId}`);
    }
    return { dashboards, dashboardDetails, selectedDashboard };
  }

  async function refreshDashboardState() {
    const dashboards = await fetchDashboards();
    const dashboardDetailEntries = await Promise.all(
      dashboards.map(async (dashboard) => [dashboard.id, await fetchDashboardDetail(dashboard.id)] as const),
    );
    const dashboardDetails = Object.fromEntries(dashboardDetailEntries);
    setState((current) => {
      if (current.status !== "ready") {
        return current;
      }
      const fallbackId = dashboards[0]?.id;
      const selectedDashboard =
        dashboardDetails[current.selectedDashboard.id] ?? (fallbackId ? dashboardDetails[fallbackId] : undefined);
      if (!selectedDashboard) {
        throw new Error("No dashboards available");
      }
      return { ...current, dashboards, dashboardDetails, selectedDashboard };
    });
  }

  async function refreshThreads(refreshDashboardsWhenIdle = false) {
    const threads = await fetchCodexThreads();
    setState((current) => current.status === "ready" ? { ...current, threads } : current);
    if (refreshDashboardsWhenIdle && !hasActiveCodexThread(threads)) {
      await refreshDashboardState();
    }
    return threads;
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

  useEffect(() => {
    if (state.status !== "ready" || !hasActiveCodexThread(state.threads)) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshThreads(true);
    }, 2_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [state]);

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

  async function handleSelectDashboard(dashboardId: string): Promise<DashboardDetail> {
    if (state.status !== "ready" || dashboardId === state.selectedDashboard.id) {
      if (state.status !== "ready") {
        throw new Error("ChartDex is not ready");
      }
      return state.selectedDashboard;
    }
    setSelection(null);
    setFocusedPanelId(null);
    const selectedDashboard = state.dashboardDetails[dashboardId] ?? await fetchDashboardDetail(dashboardId);
    setState({
      ...state,
      dashboardDetails: {
        ...state.dashboardDetails,
        [dashboardId]: selectedDashboard,
      },
      selectedDashboard,
    });
    return selectedDashboard;
  }

  async function handleFocusPanel(panelId: string) {
    if (state.status !== "ready") {
      throw new Error("ChartDex is not ready");
    }

    const targetEntry = Object.entries(state.dashboardDetails).find(([, dashboard]) =>
      dashboard.panels.some((panel) => panel.id === panelId),
    );
    if (!targetEntry) {
      throw new Error(`Panel not found: ${panelId}`);
    }

    const [dashboardId, dashboard] = targetEntry;
    if (dashboardId !== state.selectedDashboard.id) {
      setSelection(null);
      setState({ ...state, selectedDashboard: dashboard });
    }
    setFocusedPanelId(panelId);
    return { dashboardId, panelId };
  }

  function handleSelectRange(nextSelection: ChartSelection | null) {
    setSelection(nextSelection);
    setFocusedPanelId(nextSelection?.panelId ?? null);
  }

  function handleClearSelection() {
    setSelection(null);
  }

  async function handleCreateCodexThread(utterance: string, title = titleFromUtterance(utterance)): Promise<CodexThread> {
    if (state.status !== "ready") {
      throw new Error("ChartDex is not ready");
    }
    const thread = await createCodexThread({
      title,
      utterance,
      context: codexContextForCurrentView(state.selectedDashboard, selection),
    });
    setState((current) => current.status === "ready" ? { ...current, threads: upsertThread(current.threads, thread) } : current);
    void refreshThreads(true);
    return thread;
  }

  async function handleAppendCodexTurn(threadId: string, utterance: string): Promise<CodexThread> {
    const thread = await appendCodexThreadTurn(threadId, { utterance });
    setState((current) => current.status === "ready" ? { ...current, threads: upsertThread(current.threads, thread) } : current);
    void refreshThreads(true);
    return thread;
  }

  async function handleResetDemo() {
    if (state.status !== "ready") {
      throw new Error("ChartDex is not ready");
    }
    const reset = await resetDemo();
    const dashboardState = await loadDashboardState();
    const threads = await fetchCodexThreads();
    setSelection(null);
    setFocusedPanelId(null);
    setState((current) => current.status === "ready" ? { ...current, ...dashboardState, threads } : current);
    return reset;
  }

  async function handleLogout() {
    await logout();
    setSelection(null);
    setFocusedPanelId(null);
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
      dashboardDetails={state.dashboardDetails}
      focusedPanelId={focusedPanelId}
      onClearSelection={handleClearSelection}
      onLogout={handleLogout}
      onCreateCodexThread={handleCreateCodexThread}
      onAppendCodexTurn={handleAppendCodexTurn}
      onFocusPanel={handleFocusPanel}
      onResetDemo={handleResetDemo}
      onSelectDashboard={handleSelectDashboard}
      onSelectRange={handleSelectRange}
      selectedDashboard={state.selectedDashboard}
      selection={selection}
      threads={state.threads}
      user={state.user}
    />
  );
}

function DashboardShell({
  dashboards,
  dashboardDetails,
  focusedPanelId,
  onAppendCodexTurn,
  onClearSelection,
  onCreateCodexThread,
  onFocusPanel,
  onLogout,
  onResetDemo,
  onSelectDashboard,
  onSelectRange,
  selectedDashboard,
  selection,
  threads,
  user,
}: {
  dashboards: Dashboard[];
  dashboardDetails: Record<string, DashboardDetail>;
  focusedPanelId: string | null;
  onAppendCodexTurn: (threadId: string, utterance: string) => Promise<CodexThread>;
  onClearSelection: () => void;
  onCreateCodexThread: (utterance: string, title?: string) => Promise<CodexThread>;
  onFocusPanel: (panelId: string) => Promise<{ dashboardId: string; panelId: string }>;
  onLogout: () => Promise<void>;
  onResetDemo: () => Promise<{
    codex_threads_deleted: number;
    draft_dashboards_deleted: number;
    draft_panels_deleted: number;
  }>;
  onSelectDashboard: (dashboardId: string) => Promise<DashboardDetail>;
  onSelectRange: (selection: ChartSelection | null) => void;
  selectedDashboard: DashboardDetail;
  selection: ChartSelection | null;
  threads: CodexThread[];
  user: User;
}) {
  const orgDashboards = dashboards.filter((dashboard) => dashboard.space === "org");
  const personalDashboards = dashboards.filter((dashboard) => dashboard.space === "personal");
  const panelRefs = useRef(new Map<string, HTMLElement>());
  const dashboardScrollRef = useRef<HTMLDivElement>(null);
  const [codexThreadFocusRequest, setCodexThreadFocusRequest] = useState<CodexThreadFocusRequest | null>(null);
  const registerPanel = useCallback((panelId: string, element: HTMLElement | null) => {
    if (element) {
      panelRefs.current.set(panelId, element);
      return;
    }
    panelRefs.current.delete(panelId);
  }, []);
  const selectDashboardAtTop = useCallback(
    async (dashboardId: string) => {
      const dashboard = await onSelectDashboard(dashboardId);
      dashboardScrollRef.current?.scrollTo({ left: 0, top: 0 });
      return dashboard;
    },
    [onSelectDashboard],
  );
  const openCodexThread = useCallback(
    async (threadId: string) => {
      const thread = threads.find((candidate) => candidate.id === threadId);
      if (!thread) {
        throw new Error(`Codex thread not found: ${threadId}`);
      }
      setCodexThreadFocusRequest({ requestId: Date.now(), threadId });
      return thread;
    },
    [threads],
  );

  useEffect(() => {
    if (!focusedPanelId) {
      return;
    }
    panelRefs.current.get(focusedPanelId)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [focusedPanelId, selectedDashboard.id]);

  return (
    <main className="grid h-screen overflow-hidden grid-cols-[280px_minmax(520px,1fr)_392px] bg-[#050912] text-slate-100">
      <DashboardSidebar
        onLogout={onLogout}
        onSelectDashboard={selectDashboardAtTop}
        orgDashboards={orgDashboards}
        personalDashboards={personalDashboards}
        selectedDashboardId={selectedDashboard.id}
      />
      <section className="flex h-screen min-h-0 flex-col overflow-hidden border-x border-slate-800 bg-[#090e18]">
        <header className="z-10 flex min-h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-[#090e18]/95 px-8 backdrop-blur">
          <AskCodexForm compact={false} onSubmit={onCreateCodexThread} placeholder="Ask a question" />
          <ChartDexVoiceAgent
            dashboardDetails={dashboardDetails}
            dashboards={dashboards}
            focusedPanelId={focusedPanelId}
            onAppendCodexTurn={onAppendCodexTurn}
            onClearSelection={onClearSelection}
            onCreateCodexThread={onCreateCodexThread}
            onFocusPanel={onFocusPanel}
            onOpenCodexThread={openCodexThread}
            onOpenDashboard={selectDashboardAtTop}
            onResetDemo={onResetDemo}
            selectedDashboard={selectedDashboard}
            selection={selection ? codexContextForCurrentView(selectedDashboard, selection) : null}
            threads={threads}
          />
        </header>
        <div className="min-h-0 flex-1 overflow-auto" ref={dashboardScrollRef}>
          <DashboardCanvas
            dashboard={selectedDashboard}
            focusedPanelId={focusedPanelId}
            onSelectRange={onSelectRange}
            registerPanel={registerPanel}
            selection={selection}
          />
        </div>
      </section>
      <CodexPanel
        focusRequest={codexThreadFocusRequest}
        onAppendTurn={onAppendCodexTurn}
        onCreateThread={onCreateCodexThread}
        threads={threads}
      />
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
  onSelectDashboard: (dashboardId: string) => Promise<DashboardDetail>;
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
  onSelectDashboard: (dashboardId: string) => Promise<DashboardDetail>;
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
            id={`dashboard-nav-${dashboard.id}`}
            onClick={() => void onSelectDashboard(dashboard.id)}
            type="button"
          >
            <span className="text-slate-400">{dashboard.space === "org" ? "▥" : "⌁"}</span>
            <span className="truncate">{dashboard.name}</span>
            {dashboard.status === "draft" ? (
              <span className="ml-auto shrink-0 rounded border border-amber-400/30 px-1.5 py-0.5 text-[10px] uppercase text-amber-200">
                Draft
              </span>
            ) : null}
          </button>
        ))}
      </div>
    </section>
  );
}

function DashboardCanvas({
  dashboard,
  focusedPanelId,
  onSelectRange,
  registerPanel,
  selection,
}: {
  dashboard: DashboardDetail;
  focusedPanelId: string | null;
  onSelectRange: (selection: ChartSelection | null) => void;
  registerPanel: (panelId: string, element: HTMLElement | null) => void;
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
            focused={focusedPanelId === panel.id}
            key={panel.id}
            onSelectRange={onSelectRange}
            panel={panel}
            registerPanel={registerPanel}
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
  focused,
  onSelectRange,
  panel,
  registerPanel,
  selection,
}: {
  dashboardId: string;
  focused: boolean;
  onSelectRange: (selection: ChartSelection | null) => void;
  panel: DashboardPanel;
  registerPanel: (panelId: string, element: HTMLElement | null) => void;
  selection: ChartSelection | null;
}) {
  return (
    <article
      className={
        focused
          ? "rounded-md border border-blue-400 bg-slate-900/70 p-4 shadow-xl shadow-blue-950/40"
          : "rounded-md border border-slate-800 bg-slate-900/70 p-4 shadow-xl shadow-black/20"
      }
      id={`panel-${panel.id}`}
      ref={(element) => registerPanel(panel.id, element)}
    >
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
    <div className="grid grid-cols-2 overflow-hidden rounded-md border border-slate-800 md:grid-cols-3 xl:grid-cols-6">
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

function CodexPanel({
  focusRequest,
  onAppendTurn,
  onCreateThread,
  threads,
}: {
  focusRequest: CodexThreadFocusRequest | null;
  onAppendTurn: (threadId: string, utterance: string) => Promise<CodexThread>;
  onCreateThread: (utterance: string, title?: string) => Promise<CodexThread>;
  threads: CodexThread[];
}) {
  const [openThreadIds, setOpenThreadIds] = useState<Set<string>>(() => new Set());
  const [activeThreadId, setActiveThreadId] = useState(threads[0]?.id ?? null);
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const knownThreadIdsRef = useRef(new Set(threads.map((thread) => thread.id)));
  const threadScrollContainerRef = useRef<HTMLDivElement>(null);
  const threadRefs = useRef(new Map<string, HTMLElement>());
  const threadUpdateSignaturesRef = useRef(new Map(threads.map((thread) => [thread.id, threadUpdateSignature(thread)])));
  const userFocusedThreadIdRef = useRef<string | null>(null);
  const registerThread = useCallback((threadId: string, element: HTMLElement | null) => {
    if (element) {
      threadRefs.current.set(threadId, element);
      return;
    }
    threadRefs.current.delete(threadId);
  }, []);

  useEffect(() => {
    const knownThreadIds = knownThreadIdsRef.current;
    const newThreadIds = threads
      .filter((thread) => !knownThreadIds.has(thread.id))
      .map((thread) => thread.id);

    if (newThreadIds.length > 0) {
      setOpenThreadIds((current) => {
        const next = new Set(current);
        for (const threadId of newThreadIds) {
          next.add(threadId);
        }
        return next;
      });
      for (const threadId of newThreadIds) {
        knownThreadIds.add(threadId);
      }
    }

    setActiveThreadId((current) =>
      current && threads.some((thread) => thread.id === current)
        ? current
        : threads[0]?.id ?? null,
    );
  }, [threads]);

  useEffect(() => {
    if (!focusRequest) {
      return;
    }
    setActiveThreadId(focusRequest.threadId);
    setOpenThreadIds((current) => {
      const next = new Set(current);
      next.add(focusRequest.threadId);
      return next;
    });
    window.requestAnimationFrame(() => {
      threadRefs.current.get(focusRequest.threadId)?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    });
  }, [focusRequest]);

  useEffect(() => {
    const previousSignatures = threadUpdateSignaturesRef.current;
    const nextSignatures = new Map(threads.map((thread) => [thread.id, threadUpdateSignature(thread)]));
    threadUpdateSignaturesRef.current = nextSignatures;

    const changedThread = threads.find((thread) => previousSignatures.get(thread.id) !== nextSignatures.get(thread.id));
    if (!changedThread || !openThreadIds.has(changedThread.id) || activeThreadId !== changedThread.id) {
      return;
    }

    const focusedThreadId = focusedCodexThreadId();
    const userFocusedThreadId = userFocusedThreadIdRef.current ?? focusedThreadId;
    if (userFocusedThreadId && userFocusedThreadId !== changedThread.id) {
      return;
    }

    window.requestAnimationFrame(() => {
      const threadElement = threadRefs.current.get(changedThread.id);
      const scrollContainer = threadScrollContainerRef.current;
      if (!threadElement || !scrollContainer) {
        return;
      }
      threadElement.scrollIntoView({ behavior: "auto", block: "end" });
      scrollContainer.scrollTop = scrollContainer.scrollHeight;
    });
  }, [activeThreadId, openThreadIds, threads]);

  return (
    <aside
      className="flex h-screen min-h-0 flex-col overflow-hidden bg-[#060b14]"
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          userFocusedThreadIdRef.current = null;
        }
      }}
    >
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 px-5">
        <div className="text-sm font-semibold text-white">✦ Codex</div>
        <button
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-blue-500/50 hover:text-white"
          onClick={() => setIsComposerOpen((current) => !current)}
          type="button"
        >
          + New thread
        </button>
      </div>
      {isComposerOpen ? (
        <div className="shrink-0 border-b border-slate-800 p-4">
          <AskCodexForm
            compact
            onSubmit={async (utterance) => {
              await onCreateThread(utterance);
              setIsComposerOpen(false);
            }}
            placeholder="Start a Codex thread..."
          />
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto space-y-3 p-4" ref={threadScrollContainerRef}>
        {threads.length === 0 ? (
          <p className="rounded-md border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">
            No Codex threads yet.
          </p>
        ) : null}
        {threads.map((thread, index) => {
          const isOpen = openThreadIds.has(thread.id);
          const isActive = activeThreadId === thread.id;
          return (
            <article
              className={isActive ? "overflow-hidden rounded-md border border-blue-500/50 bg-slate-950" : "overflow-hidden rounded-md border border-slate-800 bg-slate-950"}
              data-codex-thread-id={thread.id}
              id={`codex-thread-${thread.id}`}
              key={thread.id}
              onFocusCapture={() => {
                userFocusedThreadIdRef.current = thread.id;
              }}
              onPointerDownCapture={() => {
                userFocusedThreadIdRef.current = thread.id;
              }}
              ref={(element) => registerThread(thread.id, element)}
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
              {isOpen ? <ThreadBody onAppendTurn={onAppendTurn} thread={thread} /> : null}
            </article>
          );
        })}
      </div>
    </aside>
  );
}

function ThreadBody({
  onAppendTurn,
  thread,
}: {
  onAppendTurn: (threadId: string, utterance: string) => Promise<CodexThread>;
  thread: CodexThread;
}) {
  const [utterance, setUtterance] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const isBusy = thread.status === "queued" || thread.status === "running";
  return (
    <div className="space-y-4 border-t border-slate-800 p-4">
      {thread.turns.length === 0 ? <p className="text-sm text-slate-500">Waiting to start.</p> : null}
      {thread.turns.map((turn) => (
        <div className={turn.role === "user" ? "rounded-md bg-slate-900 p-3" : "rounded-md bg-blue-500/5 p-3"} key={turn.id}>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{turn.role}</div>
          <MarkdownContent markdown={turn.markdown} />
        </div>
      ))}
      {thread.error_message ? <p className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{thread.error_message}</p> : null}
      <form
        className="flex gap-2 border-t border-slate-800 pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = utterance.trim();
          if (!trimmed || isBusy) {
            return;
          }
          setErrorMessage(null);
          setIsSubmitting(true);
          void onAppendTurn(thread.id, trimmed)
            .then(() => {
              setUtterance("");
            })
            .catch((error: unknown) => {
              setErrorMessage(error instanceof Error ? error.message : "Unable to send follow-up");
            })
            .finally(() => {
              setIsSubmitting(false);
            });
        }}
      >
        <input
          className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600"
          disabled={isBusy || isSubmitting}
          onChange={(event) => setUtterance(event.target.value)}
          placeholder={isBusy ? "Codex is running..." : "Ask a follow-up..."}
          value={utterance}
        />
        <button className="rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!utterance.trim() || isBusy || isSubmitting} type="submit">
          {isSubmitting ? "Sending" : "Send"}
        </button>
      </form>
      {errorMessage ? <p className="text-sm text-red-300">{errorMessage}</p> : null}
    </div>
  );
}

function AskCodexForm({
  compact,
  onSubmit,
  placeholder,
}: {
  compact: boolean;
  onSubmit: (utterance: string) => Promise<unknown>;
  placeholder: string;
}) {
  const [utterance, setUtterance] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  return (
    <form
      className={compact ? "space-y-2" : "flex w-full max-w-2xl gap-2"}
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = utterance.trim();
        if (!trimmed) {
          return;
        }
        setErrorMessage(null);
        setIsSubmitting(true);
        void onSubmit(trimmed)
          .then(() => {
            setUtterance("");
          })
          .catch((error: unknown) => {
            setErrorMessage(error instanceof Error ? error.message : "Unable to create Codex thread");
          })
          .finally(() => {
            setIsSubmitting(false);
          });
      }}
    >
      <div className={compact ? "flex gap-2" : "flex min-w-0 flex-1 gap-2"}>
        <input
          aria-label="Ask a question"
          className="h-10 min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950/80 px-4 text-sm text-slate-100 outline-none ring-blue-500/20 placeholder:text-slate-500 focus:ring-4"
          disabled={isSubmitting}
          onChange={(event) => setUtterance(event.target.value)}
          placeholder={placeholder}
          value={utterance}
        />
        <button
          className="h-10 rounded-md bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
          disabled={!utterance.trim() || isSubmitting}
          type="submit"
        >
          {isSubmitting ? "Asking" : "Ask"}
        </button>
      </div>
      {errorMessage ? <p className="text-sm text-red-300">{errorMessage}</p> : null}
    </form>
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

function hasActiveCodexThread(threads: CodexThread[]) {
  return threads.some((thread) => thread.status === "queued" || thread.status === "running");
}

function threadUpdateSignature(thread: CodexThread) {
  const lastTurn = thread.turns.at(-1);
  return [
    thread.status,
    thread.updated_at,
    thread.error_message ?? "",
    thread.turns.length,
    lastTurn?.id ?? "",
    lastTurn?.markdown.length ?? 0,
  ].join("|");
}

function focusedCodexThreadId() {
  const activeElement = document.activeElement;
  if (!(activeElement instanceof HTMLElement)) {
    return null;
  }
  return activeElement.closest("[data-codex-thread-id]")?.getAttribute("data-codex-thread-id") ?? null;
}

function upsertThread(threads: CodexThread[], nextThread: CodexThread) {
  const existingIndex = threads.findIndex((thread) => thread.id === nextThread.id);
  if (existingIndex === -1) {
    return [nextThread, ...threads];
  }
  return threads.map((thread) => thread.id === nextThread.id ? nextThread : thread);
}

function titleFromUtterance(utterance: string) {
  const trimmed = utterance.trim();
  return trimmed.length > 72 ? `${trimmed.slice(0, 69)}...` : trimmed;
}

function codexContextForCurrentView(
  dashboard: DashboardDetail,
  selection: ChartSelection | null,
): CodexThreadContext {
  if (!selection || selection.dashboardId !== dashboard.id) {
    return { dashboard_id: dashboard.id };
  }
  return {
    dashboard_id: dashboard.id,
    panel_id: selection.panelId,
    metric_key: selection.metricKey,
    range_start: selection.rangeStart,
    range_end: selection.rangeEnd,
  };
}

function formatAxisValue(value: number | string, format: DashboardPanel["value_format"]) {
  const numeric = Number(value);
  if (format === "currency") {
    return formatCompactCurrency(numeric);
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

function formatCompactCurrency(value: number) {
  const absoluteValue = Math.abs(value);
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: absoluteValue >= 1_000 ? 1 : 0,
    notation: "compact",
    style: "currency",
  }).format(value);
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
