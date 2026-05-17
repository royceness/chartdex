import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("App", () => {
  test("renders the authenticated dashboard shell with markdown threads", async () => {
    mockAuthenticatedLoad();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Checkout Funnel" })).toBeInTheDocument();
    });
    expect(screen.getByText("Org Dashboards")).toBeInTheDocument();
    expect(screen.getByText("My Dashboards")).toBeInTheDocument();
    expect(screen.getByText("Revenue Over Time")).toBeInTheDocument();
    expect(screen.getByText("Checkout Conversion Over Time")).toBeInTheDocument();
    expect(screen.getByText("✦ Codex")).toBeInTheDocument();
    expect(screen.getByText("Checkout conversion read")).toBeInTheDocument();
    expect(screen.getByText("Mermaid diagram")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/me",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  test("shows login when there is no active session", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: async () => "Not authenticated",
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    });
  });

  test("logs in and loads dashboard detail plus Codex threads", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "Not authenticated",
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: {
            user_id: "u_analyst",
            email: "analyst@acme.test",
            name: "Riley Analyst",
            org_id: "org_acme",
            role: "analyst",
          },
        }),
      });
    mockDashboardResponses();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "analyst@acme.test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Checkout Funnel" })).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        credentials: "include",
        method: "POST",
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/dashboards/dash_checkout_funnel",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});

function mockAuthenticatedLoad() {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      user: {
        user_id: "u_admin",
        email: "admin@acme.test",
        name: "Avery Admin",
        org_id: "org_acme",
        role: "admin",
      },
    }),
  });
  mockDashboardResponses();
}

function mockDashboardResponses() {
  fetchMock
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        dashboards: [
          {
            id: "dash_checkout_funnel",
            org_id: "org_acme",
            owner_user_id: null,
            slug: "checkout-funnel",
            name: "Checkout Funnel",
            space: "org",
            description: "Session-to-purchase conversion and step drop-off.",
          },
          {
            id: "dash_growth_experiments",
            org_id: "org_acme",
            owner_user_id: "u_admin",
            slug: "growth-experiments",
            name: "Growth Experiments",
            space: "personal",
            description: "Experiment rollout and segment-level performance.",
          },
        ],
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        dashboard: {
          id: "dash_checkout_funnel",
          org_id: "org_acme",
          owner_user_id: null,
          slug: "checkout-funnel",
          name: "Checkout Funnel",
          space: "org",
          description: "Session-to-purchase conversion and step drop-off.",
          time_range_label: "May 12 - Jun 10, 2026",
          panels: [
            {
              id: "panel_revenue_over_time",
              title: "Revenue Over Time",
              type: "line",
              metric_key: "revenue",
              value_format: "currency",
              data: [{ metric: "revenue", observed_on: "2026-05-12", value: 1210000 }],
            },
            {
              id: "panel_conversion_over_time",
              title: "Checkout Conversion Over Time",
              type: "line",
              metric_key: "conversion",
              value_format: "percent",
              data: [{ metric: "conversion", observed_on: "2026-05-12", value: 9.4 }],
            },
          ],
        },
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        threads: [
          {
            id: "thread_checkout_conversion",
            title: "Explain checkout conversion",
            status: "complete",
            turns: [
              {
                id: "turn_assistant",
                role: "assistant",
                markdown:
                  "### Checkout conversion read\n\n```mermaid\nflowchart LR\n  Sessions --> Purchase\n```",
                created_at: "2026-05-17T20:45:12Z",
              },
            ],
          },
        ],
      }),
    });
}
