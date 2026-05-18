import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";

import {
  GhostCursorOverlay,
  createVoiceControlController,
  useGhostCursor,
  useVoiceControl,
  type VoiceControlEvent,
  type VoiceControlController,
} from "../vendor/realtime-voice-component";
import "../vendor/realtime-voice-component/styles.css";
import type { CodexThread, CodexThreadContext, Dashboard, DashboardDetail } from "../api";
import { fetchCodexThread } from "../api";
import {
  buildChartDexVoiceContext,
  buildChartDexVoiceInstructions,
  buildChartDexVoiceTools,
  enrichCodexInvestigationUtterance,
  type ChartDexVoiceAdapter,
} from "./chartdexVoice";

export function ChartDexVoiceAgent({
  dashboardDetails,
  dashboards,
  focusedPanelId,
  onClearSelection,
  onAppendCodexTurn,
  onCreateCodexThread,
  onFocusPanel,
  onOpenCodexThread,
  onOpenDashboard,
  onResetDemo,
  selectedDashboard,
  selection,
  threads,
}: {
  dashboardDetails: Record<string, DashboardDetail>;
  dashboards: Dashboard[];
  focusedPanelId: string | null;
  onAppendCodexTurn: (threadId: string, utterance: string) => Promise<CodexThread>;
  onClearSelection: () => void;
  onCreateCodexThread: (utterance: string, title?: string) => Promise<CodexThread>;
  onFocusPanel: (panelId: string) => Promise<{ dashboardId: string; panelId: string }>;
  onOpenCodexThread: (threadId: string) => Promise<CodexThread>;
  onOpenDashboard: (dashboardId: string) => Promise<DashboardDetail>;
  onResetDemo: () => Promise<{
    codex_threads_deleted: number;
    draft_dashboards_deleted: number;
    draft_panels_deleted: number;
  }>;
  selectedDashboard: DashboardDetail;
  selection: CodexThreadContext | null;
  threads: CodexThread[];
}) {
  const { cursorState, run } = useGhostCursor();
  const lastLoggedUserTranscriptRef = useRef<string | null>(null);
  const previousThreadStatusesRef = useRef<Map<string, CodexThread["status"]> | null>(null);
  const stateRef = useRef({
    dashboardDetails,
    dashboards,
    focusedPanelId,
    selectedDashboard,
    selection,
    threads,
  });
  stateRef.current = {
    dashboardDetails,
    dashboards,
    focusedPanelId,
    selectedDashboard,
    selection,
    threads,
  };
  const currentVoiceContext = useMemo(
    () =>
      buildChartDexVoiceContext({
        dashboardDetails,
        dashboards,
        focusedPanelId,
        selectedDashboard,
        selection,
        threads,
      }),
    [dashboardDetails, dashboards, focusedPanelId, selectedDashboard, selection, threads],
  );

  const adapter = useMemo<ChartDexVoiceAdapter>(
    () => ({
      addCodexThreadTurn: async (threadId, utterance) => {
        console.info("[chartdex voice] action addCodexThreadTurn", { threadId, utterance });
        const thread = await onAppendCodexTurn(threadId, utterance);
        const result = {
          ok: true as const,
          thread_id: thread.id,
          title: thread.title,
          status: thread.status,
        };
        console.info("[chartdex voice] result addCodexThreadTurn", result);
        return result;
      },
      clearSelection: () => {
        console.info("[chartdex voice] action clearSelection");
        onClearSelection();
        const result = { ok: true as const };
        console.info("[chartdex voice] result clearSelection", result);
        return result;
      },
      createCodexInvestigation: async (title, utterance) => {
        const context = buildChartDexVoiceContext(stateRef.current);
        const enrichedUtterance = enrichCodexInvestigationUtterance(utterance, context);
        console.info("[chartdex voice] action createCodexInvestigation", {
          title,
          utterance,
          enrichedUtterance,
          context: context.chart_selection,
        });
        const thread = await onCreateCodexThread(enrichedUtterance, title);
        const result = {
          ok: true as const,
          thread_id: thread.id,
          title: thread.title,
          status: thread.status,
        };
        console.info("[chartdex voice] result createCodexInvestigation", result);
        return result;
      },
      focusPanel: async (panelId) => {
        console.info("[chartdex voice] action focusPanel", {
          currentDashboardId: stateRef.current.selectedDashboard.id,
          panelId,
        });
        const result = await onFocusPanel(panelId);
        const dashboard = stateRef.current.dashboardDetails[result.dashboardId];
        const panel = dashboard?.panels.find((candidate) => candidate.id === panelId);
        if (!dashboard || !panel) {
          throw new Error(`Panel not found: ${panelId}`);
        }
        await waitForPaint();
        await run({ element: document.getElementById(`panel-${panelId}`) }, () => undefined);
        const toolResult = {
          ok: true as const,
          dashboard_id: result.dashboardId,
          dashboard_name: dashboard.name,
          panel_id: result.panelId,
          panel_title: panel.title,
        };
        console.info("[chartdex voice] result focusPanel", toolResult);
        return toolResult;
      },
      getContext: () => {
        const context = buildChartDexVoiceContext(stateRef.current);
        console.info("[chartdex voice] action getContext", {
          current_dashboard: context.current_dashboard,
          focused_panel_id: context.focused_panel_id,
          chart_selection: context.chart_selection,
          dashboards: context.dashboards.map((dashboard) => ({
            id: dashboard.id,
            name: dashboard.name,
            panels: dashboard.panels.map((panel) => ({
              id: panel.id,
              metric_key: panel.metric_key,
              title: panel.title,
            })),
          })),
        });
        return context;
      },
      getCodexThread: async (threadId) => {
        console.info("[chartdex voice] action getCodexThread", { threadId });
        const thread = await fetchCodexThread(threadId);
        const result = { ok: true as const, thread };
        console.info("[chartdex voice] result getCodexThread", {
          thread_id: thread.id,
          title: thread.title,
          status: thread.status,
          turns: thread.turns.length,
        });
        return result;
      },
      listCodexThreads: (status) => {
        const context = buildChartDexVoiceContext(stateRef.current);
        const filteredThreads = status
          ? context.codex_threads.filter((thread) => thread.status === status)
          : context.codex_threads;
        const result = { ok: true as const, threads: filteredThreads };
        console.info("[chartdex voice] action listCodexThreads", { status, result });
        return result;
      },
      noActionRequired: (reason) => {
        const result = { ok: true as const, reason };
        console.info("[chartdex voice] action noActionRequired", result);
        return result;
      },
      openCodexThread: async (threadId) => {
        console.info("[chartdex voice] action openCodexThread", { threadId });
        const thread = await onOpenCodexThread(threadId);
        await waitForPaint();
        await run({ element: document.getElementById(`codex-thread-${threadId}`) }, () => undefined);
        const result = {
          ok: true as const,
          thread_id: thread.id,
          title: thread.title,
          status: thread.status,
        };
        console.info("[chartdex voice] result openCodexThread", result);
        return result;
      },
      openDashboard: async (dashboardId) => {
        console.info("[chartdex voice] action openDashboard", {
          currentDashboardId: stateRef.current.selectedDashboard.id,
          dashboardId,
        });
        const dashboard = await onOpenDashboard(dashboardId);
        await waitForPaint();
        await run({ element: document.getElementById(`dashboard-nav-${dashboardId}`) }, () => undefined);
        const result = { ok: true as const, dashboard_id: dashboard.id, dashboard_name: dashboard.name };
        console.info("[chartdex voice] result openDashboard", result);
        return result;
      },
      resetDemo: async () => {
        console.info("[chartdex voice] action resetDemo");
        const reset = await onResetDemo();
        const result = { ok: true as const, reset };
        console.info("[chartdex voice] result resetDemo", result);
        return result;
      },
    }),
    [
      onAppendCodexTurn,
      onClearSelection,
      onCreateCodexThread,
      onFocusPanel,
      onOpenCodexThread,
      onOpenDashboard,
      onResetDemo,
      run,
    ],
  );
  const tools = useMemo(() => buildChartDexVoiceTools(adapter), [adapter]);
  const [voiceErrorMessage, setVoiceErrorMessage] = useState<string | null>(null);
  const instructions = useMemo(
    () => buildChartDexVoiceInstructions(currentVoiceContext),
    [currentVoiceContext],
  );
  const controllerOptions = useMemo(
    () => ({
      activationMode: "vad" as const,
      auth: {
        sessionEndpoint: "/api/realtime/session",
        sessionRequestInit: {
          credentials: "include" as const,
        },
      },
      audio: {
        input: {
          turnDetection: {
            type: "server_vad" as const,
            createResponse: true,
            interruptResponse: false,
            prefixPaddingMs: 260,
            silenceDurationMs: 650,
            threshold: 0.68,
          },
        },
        output: {
          voice: "marin" as const,
        },
      },
      instructions,
      maxOutputTokens: 800 as const,
      model: "gpt-realtime-1.5" as const,
      onEvent: (event: VoiceControlEvent) => {
        logVoiceEvent(event, lastLoggedUserTranscriptRef);
      },
      onError: (error: { message: string }) => {
        console.error("[chartdex voice] error", error);
        setVoiceErrorMessage(error.message);
      },
      onToolError: (call: unknown) => {
        console.error("[chartdex voice] tool error", call);
      },
      onToolStart: (call: unknown) => {
        console.info("[chartdex voice] tool start", call);
      },
      onToolSuccess: (call: unknown) => {
        console.info("[chartdex voice] tool success", call);
      },
      outputMode: "audio" as const,
      postToolResponse: true,
      toolChoice: "auto" as const,
      tools,
    }),
    [instructions, tools],
  );
  const [controller] = useState<VoiceControlController>(() =>
    createVoiceControlController(controllerOptions),
  );
  const runtime = useVoiceControl(controller);
  const destroyTimerRef = useRef<number | null>(null);

  useEffect(() => {
    controller.configure(controllerOptions);
  }, [controller, controllerOptions]);

  useEffect(() => {
    const nextStatuses = new Map(threads.map((thread) => [thread.id, thread.status]));
    const previousStatuses = previousThreadStatusesRef.current;
    previousThreadStatusesRef.current = nextStatuses;

    if (!previousStatuses || !runtime.connected) {
      return;
    }

    const completedThreads = threads.filter((thread) => {
      const previousStatus = previousStatuses.get(thread.id);
      return (
        (previousStatus === "queued" || previousStatus === "running") &&
        (thread.status === "complete" || thread.status === "failed")
      );
    });
    if (completedThreads.length === 0) {
      return;
    }

    for (const thread of completedThreads) {
      console.info("[chartdex voice] codex thread completed", {
        thread_id: thread.id,
        title: thread.title,
        status: thread.status,
      });
      controller.sendClientEvent({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "system",
          content: [
            {
              type: "input_text",
              text:
                `Codex investigation completed: "${thread.title}" (${thread.id}) with status ${thread.status}. ` +
                "Call get_codex_thread if you need the findings, then briefly notify the user. " +
                "Use open_codex_thread if showing the thread would help.",
            },
          ],
        },
      });
      controller.requestResponse();
    }
  }, [controller, runtime.connected, threads]);

  useEffect(() => {
    if (destroyTimerRef.current !== null) {
      window.clearTimeout(destroyTimerRef.current);
      destroyTimerRef.current = null;
    }

    return () => {
      destroyTimerRef.current = window.setTimeout(() => {
        controller.destroy();
      }, 0);
    };
  }, [controller]);

  return (
    <>
      <GhostCursorOverlay state={cursorState} />
      <div className="relative ml-4 shrink-0">
        <button
          aria-label={voiceButtonLabel(runtime.status)}
          className={voiceButtonClassName(runtime.status)}
          onClick={() => {
            setVoiceErrorMessage(null);
            if (runtime.connected) {
              runtime.disconnect();
              return;
            }
            void runtime.connect();
          }}
          title={voiceErrorMessage ?? undefined}
          type="button"
        >
          <span className="h-2 w-2 rounded-full bg-current" />
          <span>{voiceButtonText(runtime.status)}</span>
        </button>
        {runtime.status === "error" && voiceErrorMessage ? (
          <div className="absolute right-0 top-12 z-20 w-80 rounded-md border border-red-400/40 bg-red-950/95 p-3 text-xs leading-5 text-red-100 shadow-xl shadow-black/40">
            {voiceErrorMessage}
          </div>
        ) : null}
      </div>
    </>
  );
}

function voiceButtonText(status: string) {
  if (status === "connecting") {
    return "Connecting";
  }
  if (status === "listening") {
    return "Listening";
  }
  if (status === "processing") {
    return "Working";
  }
  if (status === "ready") {
    return "Voice on";
  }
  if (status === "error") {
    return "Retry voice";
  }
  return "Voice";
}

function voiceButtonLabel(status: string) {
  return status === "idle" ? "Start voice control" : "Toggle voice control";
}

function voiceButtonClassName(status: string) {
  const base = "flex h-10 items-center gap-2 rounded-full border px-3 text-sm font-medium transition";
  if (status === "error") {
    return `${base} border-red-400/60 bg-red-500/15 text-red-100 hover:bg-red-500/25`;
  }
  if (status === "connecting" || status === "processing") {
    return `${base} border-amber-400/60 bg-amber-500/15 text-amber-100`;
  }
  if (status === "listening" || status === "ready") {
    return `${base} border-emerald-400/60 bg-emerald-500/15 text-emerald-100 hover:bg-emerald-500/25`;
  }
  return `${base} border-blue-400/50 bg-blue-500/20 text-blue-100 hover:bg-blue-500/30`;
}

function waitForPaint() {
  return new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => {
      resolve();
    });
  });
}

function logVoiceEvent(
  event: VoiceControlEvent,
  lastLoggedUserTranscriptRef: MutableRefObject<string | null>,
) {
  if (event.type === "voice.transport.connected" || event.type === "voice.transport.disconnected") {
    console.info("[chartdex voice] transport", event.type);
    return;
  }
  if (event.type === "voice.capture.started" || event.type === "voice.capture.stopped") {
    console.info("[chartdex voice] capture", event.type);
    return;
  }
  if (event.type === "voice.no_action") {
    console.info("[chartdex voice] no action", event.message);
    return;
  }
  if (event.type !== "conversation.item.input_audio_transcription.completed") {
    return;
  }

  const transcript = typeof event.transcript === "string" ? event.transcript.trim() : "";
  if (!transcript || transcript === lastLoggedUserTranscriptRef.current) {
    return;
  }
  lastLoggedUserTranscriptRef.current = transcript;
  console.info("[chartdex voice] user transcript", transcript);
}
