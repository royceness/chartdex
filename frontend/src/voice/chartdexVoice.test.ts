import { describe, expect, test, vi } from "vitest";

import type { CodexThread, Dashboard, DashboardDetail } from "../api";
import {
  buildChartDexVoiceContext,
  buildChartDexVoiceInstructions,
  buildChartDexVoiceTools,
  enrichCodexInvestigationUtterance,
} from "./chartdexVoice";

describe("ChartDex voice tools", () => {
  test("builds hierarchical dashboard and panel context", () => {
    const context = buildChartDexVoiceContext({
      dashboardDetails: { dash_checkout_funnel: checkoutDashboard },
      dashboards: [checkoutDashboard],
      focusedPanelId: "panel_checkout_conversion",
      selectedDashboard: checkoutDashboard,
      selection: {
        dashboard_id: "dash_checkout_funnel",
        metric_key: "checkout_conversion",
        panel_id: "panel_checkout_conversion",
        range_end: "2026-06-07",
        range_start: "2026-06-01",
      },
      threads: [codexThread],
    });

    expect(context.current_dashboard.id).toBe("dash_checkout_funnel");
    expect(context.dashboards[0].panels).toEqual([
      {
        agent_description: "Use this for conversion dips.",
        description: "Daily checkout conversion.",
        id: "panel_checkout_conversion",
        metric_key: "checkout_conversion",
        title: "Checkout Conversion",
        type: "line",
      },
    ]);
    expect(context.chart_selection?.range_start).toBe("2026-06-01");
    expect(context.codex_threads).toEqual([
      {
        id: "thread_checkout",
        status: "complete",
        title: "Explain checkout conversion",
        updated_at: "2026-06-07T10:00:00Z",
      },
    ]);
  });

  test("puts dashboard and panel ids directly into instructions", () => {
    const context = buildChartDexVoiceContext({
      dashboardDetails: { dash_checkout_funnel: checkoutDashboard },
      dashboards: [checkoutDashboard],
      focusedPanelId: null,
      selectedDashboard: checkoutDashboard,
      selection: null,
      threads: [codexThread],
    });

    const instructions = buildChartDexVoiceInstructions(context);

    expect(instructions).toContain("Panel: Checkout Conversion (panel_checkout_conversion)");
    expect(instructions).toContain("choose the best matching panel from the workspace hierarchy");
    expect(instructions).toContain("call focus_panel with that panel id");
    expect(instructions).toContain("do not stop there");
    expect(instructions).toContain("Use no_action_required_or_unclear_audio only for unclear speech");
    expect(instructions).toContain("create_codex_investigation");
    expect(instructions).toContain("Codex can create personal draft dashboards and draft panels");
    expect(instructions).toContain("If the user asks to create, draft, add, or build a panel");
    expect(instructions).toContain("Do not try to author panels yourself");
    expect(instructions).toContain("If the user asks to reset, clear, or clean up the demo, call reset_demo");
    expect(instructions).toContain("If a chart selection exists, do not ask what they mean by \"this\"");
    expect(instructions).toContain("Codex thread: Explain checkout conversion (thread_checkout)");
  });

  test("enriches Codex investigation requests with selected chart context", () => {
    const context = buildChartDexVoiceContext({
      dashboardDetails: { dash_checkout_funnel: checkoutDashboard },
      dashboards: [checkoutDashboard],
      focusedPanelId: "panel_checkout_conversion",
      selectedDashboard: checkoutDashboard,
      selection: {
        dashboard_id: "dash_checkout_funnel",
        metric_key: "checkout_conversion",
        panel_id: "panel_checkout_conversion",
        range_end: "2026-06-07",
        range_start: "2026-06-01",
      },
      threads: [],
    });

    const enriched = enrichCodexInvestigationUtterance("Can you investigate this?", context);

    expect(enriched).toContain("User request:\nCan you investigate this?");
    expect(enriched).toContain("Dashboard: Checkout Funnel (dash_checkout_funnel)");
    expect(enriched).toContain("Panel: Checkout Conversion (panel_checkout_conversion)");
    expect(enriched).toContain("Metric: checkout_conversion");
    expect(enriched).toContain("Selected date range: 2026-06-01 to 2026-06-07");
    expect(enriched).toContain("Use the UI context above as the referent");
  });

  test("delegates tool calls to the voice adapter", async () => {
    const adapter = {
      addCodexThreadTurn: vi.fn(async (threadId: string, utterance: string) => ({
        ok: true as const,
        status: "queued" as const,
        thread_id: threadId,
        title: utterance,
      })),
      clearSelection: vi.fn(() => ({ ok: true as const })),
      createCodexInvestigation: vi.fn(async (title: string, utterance: string) => ({
        ok: true as const,
        status: "queued" as const,
        thread_id: "thread_new",
        title: `${title}: ${utterance}`,
      })),
      focusPanel: vi.fn(async (panelId: string) => ({
        dashboard_id: "dash_checkout_funnel",
        dashboard_name: "Checkout Funnel",
        ok: true as const,
        panel_id: panelId,
        panel_title: "Checkout Conversion",
      })),
      getContext: vi.fn(() => ({
        chart_selection: null,
        current_dashboard: {
          agent_description: "Use checkout.",
          description: "Checkout.",
          id: "dash_checkout_funnel",
          name: "Checkout Funnel",
        },
        dashboards: [],
        focused_panel_id: null,
        codex_threads: [],
      })),
      getCodexThread: vi.fn(async (threadId: string) => ({ ok: true as const, thread: { ...codexThread, id: threadId } })),
      listCodexThreads: vi.fn(() => ({
        ok: true as const,
        threads: [],
      })),
      noActionRequired: vi.fn((reason?: string) => ({ ok: true as const, reason })),
      openCodexThread: vi.fn(async (threadId: string) => ({
        ok: true as const,
        status: "complete" as const,
        thread_id: threadId,
        title: "Explain checkout conversion",
      })),
      openDashboard: vi.fn(async (dashboardId: string) => ({
        dashboard_id: dashboardId,
        dashboard_name: "Checkout Funnel",
        ok: true as const,
      })),
      resetDemo: vi.fn(async () => ({
        ok: true as const,
        reset: {
          codex_threads_deleted: 2,
          draft_dashboards_deleted: 1,
          draft_panels_deleted: 3,
        },
      })),
    };
    const tools = buildChartDexVoiceTools(adapter);
    const createTool = tools.find((tool) => tool.name === "create_codex_investigation");

    expect(createTool?.description).toContain("create/draft/add a new panel");

    await tools.find((tool) => tool.name === "open_dashboard")?.execute({
      dashboard_id: "dash_checkout_funnel",
    });
    await tools.find((tool) => tool.name === "focus_panel")?.execute({
      panel_id: "panel_checkout_conversion",
    });
    tools.find((tool) => tool.name === "clear_chart_selection")?.execute({});
    tools.find((tool) => tool.name === "no_action_required_or_unclear_audio")?.execute({
      reason: "background noise",
    });
    await tools.find((tool) => tool.name === "create_codex_investigation")?.execute({
      title: "Investigate checkout",
      utterance: "Why did conversion dip?",
    });
    tools.find((tool) => tool.name === "list_codex_threads")?.execute({
      status: "complete",
    });
    await tools.find((tool) => tool.name === "get_codex_thread")?.execute({
      thread_id: "thread_checkout",
    });
    await tools.find((tool) => tool.name === "add_codex_thread_turn")?.execute({
      thread_id: "thread_checkout",
      utterance: "Break it down by platform.",
    });
    await tools.find((tool) => tool.name === "open_codex_thread")?.execute({
      thread_id: "thread_checkout",
    });
    await tools.find((tool) => tool.name === "reset_demo")?.execute({});

    expect(adapter.openDashboard).toHaveBeenCalledWith("dash_checkout_funnel");
    expect(adapter.focusPanel).toHaveBeenCalledWith("panel_checkout_conversion");
    expect(adapter.clearSelection).toHaveBeenCalled();
    expect(adapter.noActionRequired).toHaveBeenCalledWith("background noise");
    expect(adapter.createCodexInvestigation).toHaveBeenCalledWith("Investigate checkout", "Why did conversion dip?");
    expect(adapter.listCodexThreads).toHaveBeenCalledWith("complete");
    expect(adapter.getCodexThread).toHaveBeenCalledWith("thread_checkout");
    expect(adapter.addCodexThreadTurn).toHaveBeenCalledWith("thread_checkout", "Break it down by platform.");
    expect(adapter.openCodexThread).toHaveBeenCalledWith("thread_checkout");
    expect(adapter.resetDemo).toHaveBeenCalled();
  });
});

const checkoutDashboard = {
  agent_description: "Use Checkout Funnel for conversion health.",
  description: "Session-to-purchase conversion and step drop-off.",
  id: "dash_checkout_funnel",
  name: "Checkout Funnel",
  org_id: "org_acme",
  owner_user_id: null,
  status: "published",
  created_by: "user",
  source_thread_id: null,
  panels: [
    {
      agent_description: "Use this for conversion dips.",
      data: [{ metric: "checkout_conversion", observed_on: "2026-06-01", value: 12.4 }],
      description: "Daily checkout conversion.",
      id: "panel_checkout_conversion",
      metric_key: "checkout_conversion",
      title: "Checkout Conversion",
      type: "line",
      value_format: "percent",
    },
  ],
  slug: "checkout-funnel",
  space: "org",
  time_range_label: "2026-05-09 - 2026-06-07",
} satisfies Dashboard & DashboardDetail;

const codexThread: CodexThread = {
  context: null,
  created_at: "2026-06-07T09:55:00Z",
  error_message: null,
  external_codex_thread_id: "external_thread",
  id: "thread_checkout",
  status: "complete",
  title: "Explain checkout conversion",
  turns: [
    {
      created_at: "2026-06-07T09:55:00Z",
      id: "turn_1",
      markdown: "Explain checkout conversion",
      role: "user",
    },
  ],
  updated_at: "2026-06-07T10:00:00Z",
};
