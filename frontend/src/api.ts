export type Dashboard = {
  id: number;
  slug: string;
  name: string;
  space: "org" | "my";
  description: string;
};

export type MetricPoint = {
  metric: string;
  observed_on: string;
  value: number;
};

export async function fetchDashboards(): Promise<Dashboard[]> {
  const response = await fetch("/api/dashboards");
  if (!response.ok) {
    throw new Error(`Failed to load dashboards: ${response.status}`);
  }
  const payload = (await response.json()) as { dashboards: Dashboard[] };
  return payload.dashboards;
}

export async function fetchMetric(metric: string): Promise<MetricPoint[]> {
  const response = await fetch(`/api/metrics/${metric}`);
  if (!response.ok) {
    throw new Error(`Failed to load metric ${metric}: ${response.status}`);
  }
  const payload = (await response.json()) as { points: MetricPoint[] };
  return payload.points;
}
