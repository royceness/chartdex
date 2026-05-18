export type Dashboard = {
  id: string;
  org_id: string;
  owner_user_id: string | null;
  slug: string;
  name: string;
  space: "org" | "personal";
  status: "draft" | "published";
  created_by: "user" | "codex";
  source_thread_id: string | null;
  description: string;
  agent_description: string;
};

export type DashboardDetail = Dashboard & {
  time_range_label: string;
  panels: DashboardPanel[];
};

export type DashboardPanel =
  | {
      id: string;
      title: string;
      type: "line";
      metric_key: string;
      value_format: "currency" | "percent" | "integer";
      description: string;
      agent_description: string;
      data: MetricPoint[];
    }
  | {
      id: string;
      title: string;
      type: "bar" | "funnel";
      metric_key: string;
      value_format: "currency" | "percent" | "integer";
      description: string;
      agent_description: string;
      data: CategoryPoint[];
    };

export type User = {
  user_id: string;
  email: string;
  name: string;
  org_id: string;
  role: string;
};

export type MetricPoint = {
  metric: string;
  observed_on: string;
  value: number;
};

export type CategoryPoint = {
  label: string;
  value: number;
  rate?: number | null;
};

export type CodexThread = {
  id: string;
  title: string;
  status: "queued" | "running" | "complete" | "failed";
  external_codex_thread_id: string | null;
  error_message: string | null;
  context: CodexThreadContext | null;
  created_at: string;
  updated_at: string;
  turns: CodexTurn[];
};

export type CodexThreadContext = {
  dashboard_id?: string;
  panel_id?: string;
  metric_key?: string;
  range_start?: string;
  range_end?: string;
};

export type CodexTurn = {
  id: string;
  role: "user" | "assistant" | "tool";
  markdown: string;
  created_at: string;
};

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`, {
      cause: response.status,
    });
  }

  return (await response.json()) as T;
}

export async function fetchCurrentUser(): Promise<User> {
  const payload = await apiFetch<{ user: User }>("/api/auth/me");
  return payload.user;
}

export async function login(email: string, password: string): Promise<User> {
  const payload = await apiFetch<{ user: User }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return payload.user;
}

export async function logout(): Promise<void> {
  await apiFetch<{ ok: true }>("/api/auth/logout", { method: "POST" });
}

export async function resetDemo(): Promise<{
  codex_threads_deleted: number;
  draft_dashboards_deleted: number;
  draft_panels_deleted: number;
}> {
  const payload = await apiFetch<{
    reset: {
      codex_threads_deleted: number;
      draft_dashboards_deleted: number;
      draft_panels_deleted: number;
    };
  }>("/api/demo/reset", { method: "POST" });
  return payload.reset;
}

export async function fetchDashboards(): Promise<Dashboard[]> {
  const payload = await apiFetch<{ dashboards: Dashboard[] }>("/api/dashboards");
  return payload.dashboards;
}

export async function fetchDashboardDetail(dashboardId: string): Promise<DashboardDetail> {
  const payload = await apiFetch<{ dashboard: DashboardDetail }>(`/api/dashboards/${dashboardId}`);
  return payload.dashboard;
}

export async function fetchCodexThreads(): Promise<CodexThread[]> {
  const payload = await apiFetch<{ threads: CodexThread[] }>("/api/codex/threads");
  return payload.threads;
}

export async function fetchCodexThread(threadId: string): Promise<CodexThread> {
  const payload = await apiFetch<{ thread: CodexThread }>(`/api/codex/threads/${threadId}`);
  return payload.thread;
}

export async function createCodexThread(request: {
  title: string;
  utterance: string;
  context?: CodexThreadContext;
}): Promise<CodexThread> {
  const payload = await apiFetch<{ thread: CodexThread }>("/api/codex/threads", {
    method: "POST",
    body: JSON.stringify(request),
  });
  return payload.thread;
}

export async function appendCodexThreadTurn(
  threadId: string,
  request: { utterance: string },
): Promise<CodexThread> {
  const payload = await apiFetch<{ thread: CodexThread }>(`/api/codex/threads/${threadId}/turns`, {
    method: "POST",
    body: JSON.stringify(request),
  });
  return payload.thread;
}

export async function fetchMetric(metric: string): Promise<MetricPoint[]> {
  const payload = await apiFetch<{ points: MetricPoint[] }>(`/api/metrics/${metric}`);
  return payload.points;
}
