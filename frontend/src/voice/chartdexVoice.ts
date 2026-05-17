import { z } from "zod";

import {
  defineVoiceTool,
  type VoiceTool,
} from "../vendor/realtime-voice-component";
import type { CodexThreadContext, Dashboard, DashboardDetail, DashboardPanel } from "../api";

export type ChartDexVoiceContext = {
  dashboards: Array<{
    id: string;
    name: string;
    space: Dashboard["space"];
    description: string;
    agent_description: string;
    panels: Array<{
      id: string;
      title: string;
      type: DashboardPanel["type"];
      metric_key: string;
      description: string;
      agent_description: string;
    }>;
  }>;
  current_dashboard: {
    id: string;
    name: string;
    description: string;
    agent_description: string;
  };
  focused_panel_id: string | null;
  chart_selection: CodexThreadContext | null;
};

export type ChartDexVoiceAdapter = {
  clearSelection: () => { ok: true };
  focusPanel: (panelId: string) => Promise<{
    ok: true;
    dashboard_id: string;
    dashboard_name: string;
    panel_id: string;
    panel_title: string;
  }>;
  getContext: () => ChartDexVoiceContext;
  noActionRequired: (reason?: string) => { ok: true; reason?: string };
  openDashboard: (dashboardId: string) => Promise<{ ok: true; dashboard_id: string; dashboard_name: string }>;
};

export function buildChartDexVoiceTools(adapter: ChartDexVoiceAdapter): VoiceTool<any>[] {
  return [
    defineVoiceTool({
      name: "get_chartdex_context",
      description:
        "Get the ChartDex workspace hierarchy, current dashboard, focused panel, and chart selection. If this reveals the right dashboard or panel, continue with open_dashboard or focus_panel in the next tool call.",
      parameters: z.object({}),
      execute: () => ({
        ok: true,
        context: adapter.getContext(),
      }),
    }),
    defineVoiceTool({
      name: "open_dashboard",
      description:
        "Open a dashboard by id. Use this when the user asks to show or navigate to a dashboard.",
      parameters: z.object({
        dashboard_id: z.string().min(1),
      }),
      execute: ({ dashboard_id }) => adapter.openDashboard(dashboard_id),
    }),
    defineVoiceTool({
      name: "focus_panel",
      description:
        "Show a dashboard panel by id. Use this whenever the user asks to see a metric or panel, even if the panel belongs to a different dashboard. The app will open the owning dashboard and scroll to the panel.",
      parameters: z.object({
        panel_id: z.string().min(1),
      }),
      execute: ({ panel_id }) => adapter.focusPanel(panel_id),
    }),
    defineVoiceTool({
      name: "clear_chart_selection",
      description: "Clear the currently selected chart range.",
      parameters: z.object({}),
      execute: () => adapter.clearSelection(),
    }),
    defineVoiceTool({
      name: "no_action_required_or_unclear_audio",
      description:
        "Use only when the user audio is unclear, background noise, or unrelated to ChartDex navigation. Do not use this for dashboard, panel, metric, or chart selection requests.",
      parameters: z.object({
        reason: z.string().optional(),
      }),
      execute: ({ reason }) => adapter.noActionRequired(reason),
    }),
  ];
}

export function buildChartDexVoiceContext({
  dashboardDetails,
  dashboards,
  focusedPanelId,
  selectedDashboard,
  selection,
}: {
  dashboardDetails: Record<string, DashboardDetail>;
  dashboards: Dashboard[];
  focusedPanelId: string | null;
  selectedDashboard: DashboardDetail;
  selection: CodexThreadContext | null;
}): ChartDexVoiceContext {
  return {
    dashboards: dashboards.map((dashboard) => {
      const detail = dashboardDetails[dashboard.id];
      return {
        id: dashboard.id,
        name: dashboard.name,
        space: dashboard.space,
        description: dashboard.description,
        agent_description: dashboard.agent_description,
        panels: detail ? detail.panels.map(panelSummary) : [],
      };
    }),
    current_dashboard: {
      id: selectedDashboard.id,
      name: selectedDashboard.name,
      description: selectedDashboard.description,
      agent_description: selectedDashboard.agent_description,
    },
    focused_panel_id: focusedPanelId,
    chart_selection: selection,
  };
}

export function buildChartDexVoiceInstructions(context: ChartDexVoiceContext): string {
  const dashboardLines = context.dashboards.flatMap((dashboard) => [
    `Dashboard: ${dashboard.name} (${dashboard.id}) [${dashboard.space}]`,
    `Purpose: ${dashboard.agent_description}`,
    ...dashboard.panels.map(
      (panel) =>
        `Panel: ${panel.title} (${panel.id}) metric=${panel.metric_key} dashboard=${dashboard.id}. ${panel.agent_description}`,
    ),
  ]);
  const selectionLine = context.chart_selection
    ? `Current chart selection: dashboard=${context.chart_selection.dashboard_id ?? "none"} panel=${context.chart_selection.panel_id ?? "none"} metric=${context.chart_selection.metric_key ?? "none"} range=${context.chart_selection.range_start ?? "none"}..${context.chart_selection.range_end ?? "none"}`
    : "Current chart selection: none";

  return `
You are the ChartDex voice navigation agent.
You already have the full dashboard and panel hierarchy below. Do not search for context unless the user asks what is available or you are genuinely uncertain.
Use tools to act on the UI. Do not claim that you opened or focused something unless the tool succeeds.
If the user asks to show a panel or metric, choose the best matching panel from the workspace hierarchy and call focus_panel with that panel id.
If the requested panel is on another dashboard, focus_panel will open that dashboard and scroll there.
If you first call get_chartdex_context, do not stop there. Use the returned context to make the next required tool call.
Use no_action_required_or_unclear_audio only for unclear speech, background noise, or unrelated speech.
For navigation, do not explain your reasoning. After successful actions, say only "Done", "Got it", or "OK".
Use a longer answer only when the user explicitly asks you to explain something.
If the user asks a question that needs metric investigation, briefly say that Codex investigation is not wired to voice yet.

Current dashboard: ${context.current_dashboard.name} (${context.current_dashboard.id})
Focused panel: ${context.focused_panel_id ?? "none"}
${selectionLine}

Workspace hierarchy:
${dashboardLines.join("\n")}
`.trim();
}

function panelSummary(panel: DashboardPanel) {
  return {
    id: panel.id,
    title: panel.title,
    type: panel.type,
    metric_key: panel.metric_key,
    description: panel.description,
    agent_description: panel.agent_description,
  };
}
