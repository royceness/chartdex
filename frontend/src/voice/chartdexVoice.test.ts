import { describe, expect, test, vi } from "vitest";

import type { Dashboard, DashboardDetail } from "../api";
import {
  buildChartDexVoiceContext,
  buildChartDexVoiceInstructions,
  buildChartDexVoiceTools,
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
  });

  test("puts dashboard and panel ids directly into instructions", () => {
    const context = buildChartDexVoiceContext({
      dashboardDetails: { dash_checkout_funnel: checkoutDashboard },
      dashboards: [checkoutDashboard],
      focusedPanelId: null,
      selectedDashboard: checkoutDashboard,
      selection: null,
    });

    const instructions = buildChartDexVoiceInstructions(context);

    expect(instructions).toContain("Panel: Checkout Conversion (panel_checkout_conversion)");
    expect(instructions).toContain("choose the best matching panel from the workspace hierarchy");
    expect(instructions).toContain("call focus_panel with that panel id");
    expect(instructions).toContain("do not stop there");
    expect(instructions).toContain("Use no_action_required_or_unclear_audio only for unclear speech");
  });

  test("delegates tool calls to the voice adapter", async () => {
    const adapter = {
      clearSelection: vi.fn(() => ({ ok: true as const })),
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
      })),
      noActionRequired: vi.fn((reason?: string) => ({ ok: true as const, reason })),
      openDashboard: vi.fn(async (dashboardId: string) => ({
        dashboard_id: dashboardId,
        dashboard_name: "Checkout Funnel",
        ok: true as const,
      })),
    };
    const tools = buildChartDexVoiceTools(adapter);

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

    expect(adapter.openDashboard).toHaveBeenCalledWith("dash_checkout_funnel");
    expect(adapter.focusPanel).toHaveBeenCalledWith("panel_checkout_conversion");
    expect(adapter.clearSelection).toHaveBeenCalled();
    expect(adapter.noActionRequired).toHaveBeenCalledWith("background noise");
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
