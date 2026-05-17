from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, status

from app.database import (
    append_codex_assistant_turn,
    get_codex_thread,
    get_dashboard_detail,
    update_codex_thread_status,
)


class CodexExecutionProvider(Protocol):
    def execute_thread_turn(
        self,
        *,
        app_db_path: Path,
        thread_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        ...


class LocalDemoCodexProvider:
    def execute_thread_turn(
        self,
        *,
        app_db_path: Path,
        thread_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        update_codex_thread_status(app_db_path, thread_id=thread_id, status="running")
        try:
            thread = get_codex_thread(
                app_db_path,
                thread_id=thread_id,
                org_id=org_id,
                user_id=user_id,
            )
            if thread is None:
                raise RuntimeError(f"Codex thread not found: {thread_id}")
            append_codex_assistant_turn(
                app_db_path,
                thread_id=thread_id,
                markdown=local_demo_markdown(thread),
            )
            update_codex_thread_status(app_db_path, thread_id=thread_id, status="complete")
        except Exception as exc:
            update_codex_thread_status(
                app_db_path,
                thread_id=thread_id,
                status="failed",
                error_message=str(exc),
            )
            raise


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


def local_demo_markdown(thread: dict[str, object]) -> str:
    turns = thread["turns"]
    user_turns = [turn for turn in turns if turn["role"] == "user"]
    latest_question = user_turns[-1]["markdown"] if user_turns else thread["title"]
    context = thread["context"] or {}

    lines = [
        "### Codex investigation queued",
        "",
        f"I captured the question: {latest_question}",
    ]

    if context:
        lines.extend(["", "**Context**"])
        dashboard_id = context.get("dashboard_id")
        panel_id = context.get("panel_id")
        metric_key = context.get("metric_key")
        range_start = context.get("range_start")
        range_end = context.get("range_end")
        if dashboard_id:
            lines.append(f"- Dashboard: `{dashboard_id}`")
        if panel_id:
            lines.append(f"- Panel: `{panel_id}`")
        if metric_key:
            lines.append(f"- Metric: `{metric_key}`")
        if range_start and range_end:
            lines.append(f"- Selected range: `{range_start}` to `{range_end}`")

    lines.extend(
        [
            "",
            "This local demo response proves the browser API, auth scoping, persistence, and polling path. "
            "The external Codex app-server provider can replace this executor without changing the browser contract.",
        ]
    )
    return "\n".join(lines)


codex_execution_provider: CodexExecutionProvider = LocalDemoCodexProvider()
