import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("App", () => {
  test("renders the authenticated dashboard shell with Codex threads closed by default", async () => {
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
    expect(screen.getByText("Explain checkout conversion")).toBeInTheDocument();
    expect(screen.queryByText("Checkout conversion read")).not.toBeInTheDocument();
    expect(screen.queryByText("Mermaid diagram")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Explain checkout conversion/ }));
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

  test("creates a Codex thread from the top ask box", async () => {
    mockAuthenticatedLoad();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Checkout Funnel" })).toBeInTheDocument();
    });

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          thread: {
            ...codexThreadPayload("thread_new", "Why did revenue dip?", "queued"),
            context: { dashboard_id: "dash_checkout_funnel" },
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          threads: [codexThreadPayload("thread_new", "Why did revenue dip?", "complete")],
        }),
      });
    mockDashboardOnlyResponses();

    fireEvent.change(screen.getByLabelText("Ask a question"), {
      target: { value: "Why did revenue dip?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/codex/threads",
        expect.objectContaining({
          body: JSON.stringify({
            title: "Why did revenue dip?",
            utterance: "Why did revenue dip?",
            context: { dashboard_id: "dash_checkout_funnel" },
          }),
          credentials: "include",
          method: "POST",
        }),
      );
    });
  });

  test("sends a Codex follow-up from an open thread", async () => {
    mockAuthenticatedLoad();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Explain checkout conversion")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Explain checkout conversion/ }));

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          thread: codexThreadPayload("thread_checkout_conversion", "Explain checkout conversion", "queued"),
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          threads: [codexThreadPayload("thread_checkout_conversion", "Explain checkout conversion", "complete")],
        }),
      });
    mockDashboardOnlyResponses();

    fireEvent.change(screen.getByPlaceholderText("Ask a follow-up..."), {
      target: { value: "Break that down by platform." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/codex/threads/thread_checkout_conversion/turns",
        expect.objectContaining({
          body: JSON.stringify({ utterance: "Break that down by platform." }),
          credentials: "include",
          method: "POST",
        }),
      );
    });
  });

  test("keeps manually collapsed Codex threads collapsed when thread data refreshes", async () => {
    mockAuthenticatedLoadWithThreads([
      {
        ...codexThreadPayload("thread_collapsed", "Collapsed thread", "complete"),
        turns: [
          {
            id: "thread_collapsed_turn_assistant",
            role: "assistant",
            markdown: "Collapsed thread body should stay hidden.",
            created_at: "2026-05-17T20:45:12Z",
          },
        ],
      },
      {
        ...codexThreadPayload("thread_active", "Active thread", "complete"),
        turns: [
          {
            id: "thread_active_turn_assistant",
            role: "assistant",
            markdown: "Active thread body.",
            created_at: "2026-05-17T20:45:12Z",
          },
        ],
      },
    ]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Collapsed thread")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Collapsed thread/ }));
    expect(screen.getByText("Collapsed thread body should stay hidden.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Collapsed thread/ }));
    expect(screen.queryByText("Collapsed thread body should stay hidden.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Active thread/ }));

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          thread: codexThreadPayload("thread_active", "Active thread", "queued"),
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          threads: [
            {
              ...codexThreadPayload("thread_collapsed", "Collapsed thread", "complete"),
              turns: [
                {
                  id: "thread_collapsed_turn_assistant",
                  role: "assistant",
                  markdown: "Collapsed thread body should stay hidden.",
                  created_at: "2026-05-17T20:45:12Z",
                },
              ],
            },
            codexThreadPayload("thread_active", "Active thread", "running"),
          ],
        }),
      });

    fireEvent.change(screen.getAllByPlaceholderText("Ask a follow-up...")[0], {
      target: { value: "test" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Send" })[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/codex/threads/thread_active/turns",
        expect.objectContaining({
          body: JSON.stringify({ utterance: "test" }),
          credentials: "include",
          method: "POST",
        }),
      );
    });
    expect(screen.queryByText("Collapsed thread body should stay hidden.")).not.toBeInTheDocument();
  });

  test("auto-scrolls an active Codex thread as its response updates", async () => {
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    mockAuthenticatedLoadWithThreads([
      codexThreadWithAssistant("thread_active", "Active thread", "running", "Partial response."),
      codexThreadWithAssistant("thread_other", "Other thread", "complete", "Other response."),
    ]);

    try {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText("Active thread")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByRole("button", { name: /Active thread/ }));
      expect(screen.getByText("Partial response.")).toBeInTheDocument();

      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          threads: [
            codexThreadWithAssistant("thread_active", "Active thread", "running", "Partial response with more streamed text."),
            codexThreadWithAssistant("thread_other", "Other thread", "complete", "Other response."),
          ],
        }),
      });

      await waitFor(() => {
        expect(scrollIntoView).toHaveBeenCalled();
      }, { timeout: 3_500 });
    } finally {
      Element.prototype.scrollIntoView = originalScrollIntoView;
    }
  });

  test("does not auto-scroll a streaming thread when another thread is focused", async () => {
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    mockAuthenticatedLoadWithThreads([
      codexThreadWithAssistant("thread_active", "Active thread", "running", "Partial response."),
      codexThreadWithAssistant("thread_other", "Other thread", "complete", "Other response."),
    ]);

    try {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText("Active thread")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByRole("button", { name: /Active thread/ }));
      expect(screen.getByText("Partial response.")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Other thread/ }));
      scrollIntoView.mockClear();

      const callCountBeforeRefresh = fetchMock.mock.calls.length;
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          threads: [
            codexThreadWithAssistant("thread_active", "Active thread", "running", "Partial response with more streamed text."),
            codexThreadWithAssistant("thread_other", "Other thread", "complete", "Other response."),
          ],
        }),
      });

      await waitFor(() => {
        expect(fetchMock.mock.calls.length).toBeGreaterThan(callCountBeforeRefresh);
      }, { timeout: 3_500 });
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      Element.prototype.scrollIntoView = originalScrollIntoView;
    }
  });
});

function mockAuthenticatedLoad() {
  mockAuthenticatedLoadWithThreads([
    {
      ...codexThreadPayload("thread_checkout_conversion", "Explain checkout conversion", "complete"),
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
  ]);
}

function mockAuthenticatedLoadWithThreads(threads: ReturnType<typeof codexThreadPayload>[]) {
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
  mockDashboardResponses(threads);
}

function mockDashboardResponses(threads: ReturnType<typeof codexThreadPayload>[] = []) {
  mockDashboardOnlyResponses();
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      threads,
    }),
  });
}

function mockDashboardOnlyResponses() {
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
            status: "published",
            created_by: "user",
            source_thread_id: null,
            description: "Session-to-purchase conversion and step drop-off.",
            agent_description: "Use Checkout Funnel for conversion health.",
          },
          {
            id: "dash_growth_experiments",
            org_id: "org_acme",
            owner_user_id: "u_admin",
            slug: "growth-experiments",
            name: "Growth Experiments",
            space: "personal",
            status: "published",
            created_by: "user",
            source_thread_id: null,
            description: "Experiment rollout and segment-level performance.",
            agent_description: "Use Growth Experiments for experiment analysis.",
          },
        ],
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        dashboard: checkoutDashboardDetail(),
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        dashboard: {
          ...checkoutDashboardDetail(),
          id: "dash_growth_experiments",
          owner_user_id: "u_admin",
          slug: "growth-experiments",
          name: "Growth Experiments",
          space: "personal",
          status: "published",
          created_by: "user",
          source_thread_id: null,
          description: "Experiment rollout and segment-level performance.",
          agent_description: "Use Growth Experiments for experiment analysis.",
        },
      }),
    });
}

function checkoutDashboardDetail() {
  return {
    id: "dash_checkout_funnel",
    org_id: "org_acme",
    owner_user_id: null,
    slug: "checkout-funnel",
    name: "Checkout Funnel",
    space: "org",
    status: "published",
    created_by: "user",
    source_thread_id: null,
    description: "Session-to-purchase conversion and step drop-off.",
    agent_description: "Use Checkout Funnel for conversion health.",
    time_range_label: "May 12 - Jun 10, 2026",
    panels: [
      {
        id: "panel_revenue_over_time",
        title: "Revenue Over Time",
        type: "line",
        metric_key: "revenue",
        value_format: "currency",
        description: "Daily revenue.",
        agent_description: "Use this panel for revenue trend questions.",
        data: [{ metric: "revenue", observed_on: "2026-05-12", value: 1210000 }],
      },
      {
        id: "panel_conversion_over_time",
        title: "Checkout Conversion Over Time",
        type: "line",
        metric_key: "conversion",
        value_format: "percent",
        description: "Daily conversion.",
        agent_description: "Use this panel for conversion trend questions.",
        data: [{ metric: "conversion", observed_on: "2026-05-12", value: 9.4 }],
      },
    ],
  };
}

function codexThreadPayload(id: string, title: string, status: "queued" | "running" | "complete" | "failed") {
  return {
    id,
    title,
    status,
    error_message: null,
    context: null,
    created_at: "2026-05-17T20:45:00Z",
    updated_at: "2026-05-17T20:45:12Z",
    turns: [
      {
        id: `${id}_turn_user`,
        role: "user",
        markdown: title,
        created_at: "2026-05-17T20:45:00Z",
      },
    ],
  };
}

function codexThreadWithAssistant(
  id: string,
  title: string,
  status: "queued" | "running" | "complete" | "failed",
  assistantMarkdown: string,
) {
  return {
    ...codexThreadPayload(id, title, status),
    updated_at: `2026-05-17T20:45:${assistantMarkdown.length}Z`,
    turns: [
      ...codexThreadPayload(id, title, status).turns,
      {
        id: `${id}_turn_assistant`,
        role: "assistant",
        markdown: assistantMarkdown,
        created_at: "2026-05-17T20:45:12Z",
      },
    ],
  };
}
