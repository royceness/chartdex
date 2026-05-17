import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("App", () => {
  test("renders dashboards and revenue chart once session data loads", async () => {
    fetchMock
      .mockResolvedValueOnce({
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
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          dashboards: [
            {
              id: "dash_revenue_overview",
              org_id: "org_acme",
              owner_user_id: null,
              slug: "revenue-overview",
              name: "Revenue Overview",
              space: "org",
              description: "Revenue, orders, and average order value.",
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          points: [
            { metric: "revenue", observed_on: "2026-05-11", value: 128400 },
          ],
        }),
      });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Revenue Overview")).toBeInTheDocument();
    });
    expect(screen.getByText("Avery Admin · admin")).toBeInTheDocument();
    expect(screen.getByText("Revenue, orders, and average order value.")).toBeInTheDocument();
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

  test("logs in and renders dashboards", async () => {
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
      })
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
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          points: [
            { metric: "revenue", observed_on: "2026-05-11", value: 128400 },
          ],
        }),
      });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "analyst@acme.test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByText("Riley Analyst · analyst")).toBeInTheDocument();
    });
    expect(screen.getByText("Checkout Funnel")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        credentials: "include",
        method: "POST",
      }),
    );
  });
});
