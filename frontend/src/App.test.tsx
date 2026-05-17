import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("App", () => {
  test("renders dashboards and revenue chart once backend data loads", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          dashboards: [
            {
              id: 1,
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

    expect(screen.getByText("Loading dashboards...")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Revenue Overview")).toBeInTheDocument();
    });
    expect(screen.getByText("Revenue, orders, and average order value.")).toBeInTheDocument();
  });

  test("shows backend errors", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500 });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load dashboards: 500")).toBeInTheDocument();
    });
  });
});
