import { z } from "zod";

import {
  defineVoiceTool,
  type VoiceTool,
} from "../vendor/realtime-voice-component";
import type { CodexThread, CodexThreadContext, Dashboard, DashboardDetail, DashboardPanel } from "../api";

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
  codex_threads: Array<{
    id: string;
    title: string;
    status: CodexThread["status"];
    updated_at: string;
  }>;
};

export type ChartDexVoiceAdapter = {
  addCodexThreadTurn: (threadId: string, utterance: string) => Promise<{
    ok: true;
    thread_id: string;
    title: string;
    status: CodexThread["status"];
  }>;
  clearSelection: () => { ok: true };
  createCodexInvestigation: (title: string, utterance: string) => Promise<{
    ok: true;
    thread_id: string;
    title: string;
    status: CodexThread["status"];
  }>;
  focusPanel: (panelId: string) => Promise<{
    ok: true;
    dashboard_id: string;
    dashboard_name: string;
    panel_id: string;
    panel_title: string;
  }>;
  getContext: () => ChartDexVoiceContext;
  getCodexThread: (threadId: string) => Promise<{
    ok: true;
    thread: CodexThread;
  }>;
  listCodexThreads: (status?: CodexThread["status"]) => {
    ok: true;
    threads: ChartDexVoiceContext["codex_threads"];
  };
  noActionRequired: (reason?: string) => { ok: true; reason?: string };
  openCodexThread: (threadId: string) => Promise<{
    ok: true;
    thread_id: string;
    title: string;
    status: CodexThread["status"];
  }>;
  openDashboard: (dashboardId: string) => Promise<{ ok: true; dashboard_id: string; dashboard_name: string }>;
  resetDemo: () => Promise<{
    ok: true;
    reset: {
      codex_threads_deleted: number;
      draft_dashboards_deleted: number;
      draft_panels_deleted: number;
    };
  }>;
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
      name: "create_codex_investigation",
      description:
        "Create an asynchronous Codex thread for deeper metric analysis or dashboard authoring. Use this when the user asks Codex to investigate metrics, explain anomalies, or create/draft/add a new panel, chart, or dashboard. For requests like 'investigate this' or 'what caused this dip', use the current chart selection and focused panel as the referent instead of asking for clarification. The app will attach and restate the current dashboard, focused panel, metric, and selected chart range context.",
      parameters: z.object({
        title: z.string().min(1).max(120),
        utterance: z.string().min(1).max(4000),
      }),
      execute: ({ title, utterance }) => adapter.createCodexInvestigation(title, utterance),
    }),
    defineVoiceTool({
      name: "list_codex_threads",
      description: "List Codex investigation thread summaries visible in the right panel.",
      parameters: z.object({
        status: z.enum(["queued", "running", "complete", "failed"]).optional(),
      }),
      execute: ({ status }) => adapter.listCodexThreads(status),
    }),
    defineVoiceTool({
      name: "get_codex_thread",
      description:
        "Read the full Markdown turns for a Codex investigation thread. Use this before summarizing a completed investigation or answering from a thread's findings.",
      parameters: z.object({
        thread_id: z.string().min(1),
      }),
      execute: ({ thread_id }) => adapter.getCodexThread(thread_id),
    }),
    defineVoiceTool({
      name: "add_codex_thread_turn",
      description:
        "Add a follow-up question to an existing completed or failed Codex investigation thread. The backend will queue another asynchronous Codex turn.",
      parameters: z.object({
        thread_id: z.string().min(1),
        utterance: z.string().min(1).max(4000),
      }),
      execute: ({ thread_id, utterance }) => adapter.addCodexThreadTurn(thread_id, utterance),
    }),
    defineVoiceTool({
      name: "open_codex_thread",
      description: "Open and focus a Codex investigation thread in the right panel.",
      parameters: z.object({
        thread_id: z.string().min(1),
      }),
      execute: ({ thread_id }) => adapter.openCodexThread(thread_id),
    }),
    defineVoiceTool({
      name: "reset_demo",
      description:
        "Reset the signed-in user's demo workspace by clearing Codex threads, draft dashboards, and draft panels. Use this when the user says reset my demo, clear demo state, clean up the demo, or similar.",
      parameters: z.object({}),
      execute: () => adapter.resetDemo(),
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
  threads,
  focusedPanelId,
  selectedDashboard,
  selection,
}: {
  dashboardDetails: Record<string, DashboardDetail>;
  dashboards: Dashboard[];
  threads: CodexThread[];
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
    codex_threads: threads.map((thread) => ({
      id: thread.id,
      title: thread.title,
      status: thread.status,
      updated_at: thread.updated_at,
    })),
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
  const threadLines = context.codex_threads.map(
    (thread) => `Codex thread: ${thread.title} (${thread.id}) status=${thread.status} updated=${thread.updated_at}`,
  );

  return `
You are the ChartDex voice navigation agent.
You already have the full dashboard and panel hierarchy below. Do not search for context unless the user asks what is available or you are genuinely uncertain.
Use tools to act on the UI. Do not claim that you opened or focused something unless the tool succeeds.
If the user asks to show a panel or metric, choose the best matching panel from the workspace hierarchy and call focus_panel with that panel id.
If the requested panel is on another dashboard, focus_panel will open that dashboard and scroll there.
If the user says "this", "that", "the selected range", "this dip", "this spike", or similar, resolve it from Current chart selection and Focused panel. If a chart selection exists, do not ask what they mean by "this".
If you first call get_chartdex_context, do not stop there. Use the returned context to make the next required tool call.
Use no_action_required_or_unclear_audio only for unclear speech, background noise, or unrelated speech.
For navigation, do not explain your reasoning. After successful actions, say only "Done", "Got it", or "OK".
Use a longer answer only when the user explicitly asks you to explain something.
If the user asks a question that needs deeper metric, anomaly, experiment, business event, or dashboard analysis, call create_codex_investigation. The utterance you pass must be explicit enough for backend Codex: include the dashboard, panel, metric, and selected date range when known. Tell the user it will take a bit and keep the spoken acknowledgement brief.
Codex can create personal draft dashboards and draft panels. If the user asks to create, draft, add, or build a panel, chart, or dashboard, call create_codex_investigation with the requested authoring task. Do not try to author panels yourself.
Do not do deep metric investigations yourself. Codex investigation threads have backend access to ChartDex metrics and dashboard authoring tools.
When a Codex investigation completes, call get_codex_thread before summarizing it. Give only a very brief summary unless the user asks for detail.
If the user asks a follow-up about an existing Codex investigation, call get_codex_thread first if needed. If the follow-up requires more backend analysis, call add_codex_thread_turn.
If the user asks to reset, clear, or clean up the demo, call reset_demo. After it succeeds, say only "Done".

Current dashboard: ${context.current_dashboard.name} (${context.current_dashboard.id})
Focused panel: ${context.focused_panel_id ?? "none"}
${selectionLine}

Workspace hierarchy:
${dashboardLines.join("\n")}

Codex investigations:
${threadLines.length > 0 ? threadLines.join("\n") : "none"}
`.trim();
}

export function enrichCodexInvestigationUtterance(
  utterance: string,
  context: ChartDexVoiceContext,
): string {
  const dashboardId = context.chart_selection?.dashboard_id ?? context.current_dashboard.id;
  const dashboard = context.dashboards.find((candidate) => candidate.id === dashboardId);
  const panelId = context.chart_selection?.panel_id ?? context.focused_panel_id;
  const panel = dashboard?.panels.find((candidate) => candidate.id === panelId)
    ?? context.dashboards.flatMap((candidate) => candidate.panels).find((candidate) => candidate.id === panelId);
  const metricKey = context.chart_selection?.metric_key ?? panel?.metric_key;

  const contextLines = [
    `- Dashboard: ${dashboard?.name ?? context.current_dashboard.name} (${dashboardId})`,
  ];
  if (panel) {
    contextLines.push(`- Panel: ${panel.title} (${panel.id})`);
  } else if (panelId) {
    contextLines.push(`- Panel id: ${panelId}`);
  }
  if (metricKey) {
    contextLines.push(`- Metric: ${metricKey}`);
  }
  if (context.chart_selection?.range_start && context.chart_selection.range_end) {
    contextLines.push(
      `- Selected date range: ${context.chart_selection.range_start} to ${context.chart_selection.range_end}`,
    );
  }

  return [
    `User request:\n${utterance.trim()}`,
    `Current ChartDex UI context:\n${contextLines.join("\n")}`,
    "Use the UI context above as the referent for words like this, that, selected range, dip, or spike.",
  ].join("\n\n");
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
