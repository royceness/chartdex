from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, status

from app.codex_agent import CodexAgent, CodexAgentError, CodexAppServerAgentPool
from app.codex_tools import ChartDexToolContext
from app.database import (
    append_codex_assistant_turn,
    append_codex_turn_delta,
    get_codex_thread,
    get_dashboard_detail,
    replace_codex_turn_markdown,
    update_codex_thread_status,
)


class CodexExecutionProvider(Protocol):
    async def execute_thread_turn(
        self,
        *,
        app_db_path: Path,
        thread_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        ...

    async def close(self) -> None:
        ...


@dataclass
class AppServerCodexProvider:
    agent: CodexAgent

    async def execute_thread_turn(
        self,
        *,
        app_db_path: Path,
        thread_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        assistant_turn_id = append_codex_assistant_turn(
            app_db_path,
            thread_id=thread_id,
            markdown="",
        )
        update_codex_thread_status(app_db_path, thread_id=thread_id, status="running")
        try:
            thread = require_thread(app_db_path, thread_id=thread_id, org_id=org_id, user_id=user_id)
            latest_question = latest_user_question(thread)
            tool_context = ChartDexToolContext(
                app_db_path=app_db_path,
                org_id=org_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            on_delta = build_delta_handler(app_db_path, assistant_turn_id)
            external_thread_id = thread["external_codex_thread_id"]
            if external_thread_id:
                try:
                    result = await self.agent.continue_thread(
                        str(external_thread_id),
                        build_follow_up_codex_prompt(latest_question),
                        tool_context,
                        on_delta=on_delta,
                    )
                except CodexAgentError as exc:
                    if not is_missing_external_thread_error(exc):
                        raise
                    result = await self.agent.run_thread(
                        str(thread["title"]),
                        build_recovered_thread_prompt(thread, latest_question),
                        tool_context,
                        on_delta=on_delta,
                    )
            else:
                prompt = (
                    build_initial_codex_prompt(latest_question, thread["context"])
                    if is_initial_thread_execution(thread)
                    else build_recovered_thread_prompt(thread, latest_question)
                )
                result = await self.agent.run_thread(
                    str(thread["title"]),
                    prompt,
                    tool_context,
                    on_delta=on_delta,
                )
            replace_codex_turn_markdown(app_db_path, turn_id=assistant_turn_id, markdown=result.markdown)
            update_codex_thread_status(
                app_db_path,
                thread_id=thread_id,
                status="complete",
                external_codex_thread_id=result.external_thread_id,
            )
        except Exception as exc:
            update_codex_thread_status(
                app_db_path,
                thread_id=thread_id,
                status="failed",
                error_message=str(exc),
            )
            replace_codex_turn_markdown(
                app_db_path,
                turn_id=assistant_turn_id,
                markdown=f"Codex failed: {exc}",
            )
            raise

    async def close(self) -> None:
        await self.agent.close()


def build_delta_handler(app_db_path: Path, assistant_turn_id: str) -> Callable[[str], Awaitable[None]]:
    async def on_delta(delta: str) -> None:
        append_codex_turn_delta(app_db_path, turn_id=assistant_turn_id, delta=delta)

    return on_delta


def require_thread(
    app_db_path: Path,
    *,
    thread_id: str,
    org_id: str,
    user_id: str,
) -> dict[str, object]:
    thread = get_codex_thread(app_db_path, thread_id=thread_id, org_id=org_id, user_id=user_id)
    if thread is None:
        raise RuntimeError(f"Codex thread not found: {thread_id}")
    return thread


def latest_user_question(thread: dict[str, object]) -> str:
    turns = thread["turns"]
    if not isinstance(turns, list):
        raise RuntimeError("Codex thread turns are invalid")
    user_turns = [turn for turn in turns if isinstance(turn, dict) and turn.get("role") == "user"]
    if not user_turns:
        raise RuntimeError("Codex thread has no user turn")
    markdown = user_turns[-1].get("markdown")
    if not isinstance(markdown, str) or not markdown:
        raise RuntimeError("Latest user turn is empty")
    return markdown


def validate_codex_context(
    app_db_path: Path,
    *,
    org_id: str,
    user_id: str,
    context: dict[str, str | None] | None,
) -> dict[str, str] | None:
    if context is None:
        return None

    normalized = {key: value for key, value in context.items() if value is not None}
    if not normalized:
        return None

    unsupported = set(normalized) - {"dashboard_id", "panel_id", "metric_key", "range_start", "range_end"}
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported context fields: {', '.join(sorted(unsupported))}",
        )

    dashboard_id = normalized.get("dashboard_id")
    panel_id = normalized.get("panel_id")
    metric_key = normalized.get("metric_key")
    range_start = normalized.get("range_start")
    range_end = normalized.get("range_end")

    if panel_id and not dashboard_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="panel_id requires dashboard_id",
        )
    if metric_key and not dashboard_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metric_key requires dashboard_id",
        )
    if bool(range_start) != bool(range_end):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="range_start and range_end must be provided together",
        )
    if range_start and range_end:
        parsed_start = parse_context_date(range_start, "range_start")
        parsed_end = parse_context_date(range_end, "range_end")
        if parsed_start > parsed_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="range_start must be before or equal to range_end",
            )

    if not dashboard_id:
        return normalized

    dashboard = get_dashboard_detail(
        app_db_path,
        dashboard_id=dashboard_id,
        org_id=org_id,
        user_id=user_id,
    )
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")

    panels = dashboard["panels"]
    if panel_id:
        matching_panel = next((panel for panel in panels if panel["id"] == panel_id), None)
        if matching_panel is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Panel does not belong to dashboard",
            )
        if metric_key and matching_panel["metric_key"] != metric_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metric_key does not match panel",
            )
    elif metric_key and all(panel["metric_key"] != metric_key for panel in panels):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metric_key does not belong to dashboard",
        )

    return normalized


def parse_context_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must use YYYY-MM-DD",
        ) from exc


def build_initial_codex_prompt(question: str, context: object) -> str:
    return "\n\n".join(
        [
            f"User message:\n{question}",
            f"Validated ChartDex context snapshot:\n{json.dumps(context or {}, sort_keys=True, default=str)}",
            (
                "Only treat this as an analytics investigation if the user asks an analytics, "
                "dashboard, metric, experiment, anomaly, or business event question. "
                "For smoke tests, greetings, acknowledgements, or other non-analytics "
                "messages, answer directly and briefly without calling tools. If you do make "
                "factual claims about ChartDex data, use ChartDex tools first."
            ),
        ]
    )


def build_follow_up_codex_prompt(question: str) -> str:
    return "\n\n".join(
        [
            f"Follow-up message:\n{question}",
            (
                "Continue the existing ChartDex investigation only if this message asks an "
                "analytics, dashboard, metric, experiment, anomaly, or business event question. "
                "For smoke tests, greetings, acknowledgements, or "
                "other non-analytics messages, answer directly and briefly without calling tools. "
                "Use tools for any new factual claims about ChartDex data."
            ),
        ]
    )


def build_recovered_thread_prompt(thread: dict[str, object], latest_question: str) -> str:
    return "\n\n".join(
        [
            "The previous external Codex app-server thread is unavailable, likely because the app server restarted.",
            "Reconstruct the ChartDex investigation from this persisted conversation history:",
            persisted_thread_history(thread),
            build_follow_up_codex_prompt(latest_question),
        ]
    )


def persisted_thread_history(thread: dict[str, object]) -> str:
    turns = thread["turns"]
    if not isinstance(turns, list):
        raise RuntimeError("Codex thread turns are invalid")
    rendered_turns = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        markdown = turn.get("markdown")
        if role not in {"user", "assistant"} or not isinstance(markdown, str) or not markdown.strip():
            continue
        rendered_turns.append(f"{str(role).upper()}:\n{markdown.strip()}")
    return "\n\n".join(rendered_turns)


def is_initial_thread_execution(thread: dict[str, object]) -> bool:
    turns = thread["turns"]
    if not isinstance(turns, list):
        raise RuntimeError("Codex thread turns are invalid")
    user_turns = [turn for turn in turns if isinstance(turn, dict) and turn.get("role") == "user"]
    assistant_turns = [
        turn
        for turn in turns
        if isinstance(turn, dict) and turn.get("role") == "assistant" and str(turn.get("markdown") or "").strip()
    ]
    return len(user_turns) == 1 and not assistant_turns


def is_missing_external_thread_error(error: CodexAgentError) -> bool:
    return "thread not found" in str(error).lower()


codex_execution_provider: CodexExecutionProvider = AppServerCodexProvider(
    CodexAppServerAgentPool(cwd=Path(__file__).resolve().parents[2])
)
