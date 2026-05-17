export type Dashboard = {
  id: string;
  org_id: string;
  owner_user_id: string | null;
  slug: string;
  name: string;
  space: "org" | "personal";
  description: string;
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
      data: MetricPoint[];
    }
  | {
      id: string;
      title: string;
      type: "bar" | "funnel";
      metric_key: string;
      value_format: "currency" | "percent" | "integer";
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
  turns: CodexTurn[];
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

export async function fetchMetric(metric: string): Promise<MetricPoint[]> {
  const payload = await apiFetch<{ points: MetricPoint[] }>(`/api/metrics/${metric}`);
  return payload.points;
}
