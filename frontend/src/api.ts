export type Dashboard = {
  id: string;
  org_id: string;
  owner_user_id: string | null;
  slug: string;
  name: string;
  space: "org" | "personal";
  description: string;
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

export async function fetchMetric(metric: string): Promise<MetricPoint[]> {
  const payload = await apiFetch<{ points: MetricPoint[] }>(`/api/metrics/${metric}`);
  return payload.points;
}
