from __future__ import annotations

import asyncio
import json
import os
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.codex_tools import ChartDexToolContext, dynamic_tool_specs, handle_tool_call


class CodexAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexAgentResult:
    external_thread_id: str
    markdown: str


class CodexAgent(Protocol):
    async def run_thread(
        self,
        title: str,
        prompt: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodexAgentResult:
        ...

    async def continue_thread(
        self,
        external_thread_id: str,
        prompt: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodexAgentResult:
        ...

    async def close(self) -> None:
        ...


class CodexAppServerAgent:
    default_command = "codex space app-server"
    default_model = "gpt-5.4-mini"
    default_service_tier = "fast"
    default_reasoning_effort = "low"
    stdio_limit = 10 * 1024 * 1024

    def __init__(self, command: str | None = None, cwd: Path | None = None) -> None:
        self.command = command or os.environ.get("CHARTDEX_CODEX_COMMAND", self.default_command)
        self.cwd = cwd or Path.cwd()
        self.model = os.environ.get("CHARTDEX_CODEX_MODEL", self.default_model)
        self.service_tier = os.environ.get("CHARTDEX_CODEX_SERVICE_TIER", self.default_service_tier)
        self.reasoning_effort = os.environ.get("CHARTDEX_CODEX_REASONING_EFFORT", self.default_reasoning_effort)
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def run_thread(
        self,
        title: str,
        prompt: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodexAgentResult:
        async with self._lock:
            await self._ensure_started()
            thread_response = await self._request("thread/start", self._thread_start_params(title))
            external_thread_id = thread_response["result"]["thread"]["id"]
            await self._request("turn/start", self._turn_start_params(external_thread_id, prompt))
            markdown = await self._collect_turn(external_thread_id, tool_context, on_delta)
            return CodexAgentResult(external_thread_id=external_thread_id, markdown=markdown)

    async def continue_thread(
        self,
        external_thread_id: str,
        prompt: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodexAgentResult:
        async with self._lock:
            await self._ensure_started()
            await self._request("turn/start", self._turn_start_params(external_thread_id, prompt))
            markdown = await self._collect_turn(external_thread_id, tool_context, on_delta)
            return CodexAgentResult(external_thread_id=external_thread_id, markdown=markdown)

    async def close(self) -> None:
        async with self._lock:
            await self._terminate()

    async def start(self) -> None:
        async with self._lock:
            await self._ensure_started()

    async def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        argv = shlex.split(self.command)
        if not argv:
            raise CodexAgentError("CHARTDEX_CODEX_COMMAND must not be empty")
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self.stdio_limit,
        )
        self._next_id = 1
        await self._request(
            "initialize",
            {
                "clientInfo": {"name": "chartdex", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        await self._send({"id": request_id, "method": method, "params": params})
        return await self._response(request_id)

    def _thread_start_params(self, title: str) -> dict[str, Any]:
        return {
            "cwd": str(self.cwd),
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "ephemeral": True,
            "model": self.model,
            "serviceTier": self.service_tier,
            "baseInstructions": base_instructions(title),
            "dynamicTools": dynamic_tool_specs(),
            "experimentalRawEvents": False,
            "persistExtendedHistory": False,
        }

    def _turn_start_params(self, external_thread_id: str, prompt: str) -> dict[str, Any]:
        return {
            "threadId": external_thread_id,
            "cwd": str(self.cwd),
            "approvalPolicy": "never",
            "model": self.model,
            "serviceTier": self.service_tier,
            "effort": self.reasoning_effort,
            "input": [{"type": "text", "text": prompt, "text_elements": []}],
        }

    async def _send(self, message: dict[str, Any]) -> None:
        proc = self._active_proc()
        if proc.stdin is None:
            raise CodexAgentError("Codex app-server stdin is unavailable")
        proc.stdin.write((json.dumps(message) + "\n").encode())
        await proc.stdin.drain()

    async def _response(self, request_id: int) -> dict[str, Any]:
        while True:
            message = await self._read_message()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexAgentError(f"Codex app-server request failed: {message['error']}")
            return message

    async def _collect_turn(
        self,
        external_thread_id: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None,
    ) -> str:
        deltas: list[str] = []
        while True:
            message = await self._read_message(timeout=300)
            method = message.get("method")
            params = message.get("params") or {}
            if method == "item/agentMessage/delta" and params.get("threadId") == external_thread_id:
                delta = params.get("delta", "")
                deltas.append(delta)
                if on_delta is not None and delta:
                    await on_delta(delta)
            elif method == "item/tool/call":
                await self._handle_dynamic_tool_request(message, tool_context)
            elif method == "turn/completed" and params.get("threadId") == external_thread_id:
                turn = params.get("turn") or {}
                if turn.get("status") == "failed":
                    raise CodexAgentError(f"Codex turn failed: {turn.get('error')}")
                return "".join(deltas).strip()
            elif method == "error":
                raise CodexAgentError(str(params))

    async def _handle_dynamic_tool_request(
        self,
        message: dict[str, Any],
        tool_context: ChartDexToolContext,
    ) -> None:
        params = message.get("params") or {}
        try:
            text = await handle_tool_call(
                tool_context,
                params.get("namespace"),
                params.get("tool", ""),
                params.get("arguments"),
            )
            result = {"contentItems": [{"type": "inputText", "text": text}], "success": True}
        except Exception as exc:
            result = {"contentItems": [{"type": "inputText", "text": str(exc)}], "success": False}
        await self._send({"id": message["id"], "result": result})

    async def _read_message(self, timeout: int = 60) -> dict[str, Any]:
        proc = self._active_proc()
        if proc.stdout is None:
            raise CodexAgentError("Codex app-server stdout is unavailable")
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        except TimeoutError as exc:
            raise CodexAgentError("Timed out waiting for Codex app-server") from exc
        if not line:
            stderr = ""
            if proc.stderr is not None:
                stderr = (await proc.stderr.read()).decode(errors="replace").strip()
            raise CodexAgentError(f"Codex app-server exited unexpectedly: {stderr}")
        return json.loads(line)

    def _active_proc(self) -> asyncio.subprocess.Process:
        if self._proc is None:
            raise CodexAgentError("Codex app-server is not started")
        return self._proc

    async def _terminate(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()
            await proc.wait()


class CodexAppServerAgentPool:
    def __init__(self, command: str | None = None, concurrency: int | None = None, cwd: Path | None = None) -> None:
        self.concurrency = concurrency if concurrency is not None else int(os.environ.get("CHARTDEX_CODEX_CONCURRENCY", "1"))
        if self.concurrency < 1:
            raise ValueError("CHARTDEX_CODEX_CONCURRENCY must be at least 1")
        self._workers = [CodexAppServerAgent(command=command, cwd=cwd) for _ in range(self.concurrency)]
        self._available: asyncio.Queue[CodexAppServerAgent] = asyncio.Queue()
        for worker in self._workers:
            self._available.put_nowait(worker)

    async def run_thread(
        self,
        title: str,
        prompt: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodexAgentResult:
        worker = await self._available.get()
        try:
            return await worker.run_thread(title, prompt, tool_context, on_delta)
        finally:
            self._available.put_nowait(worker)

    async def continue_thread(
        self,
        external_thread_id: str,
        prompt: str,
        tool_context: ChartDexToolContext,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodexAgentResult:
        worker = await self._available.get()
        try:
            return await worker.continue_thread(external_thread_id, prompt, tool_context, on_delta)
        finally:
            self._available.put_nowait(worker)

    async def close(self) -> None:
        await asyncio.gather(*(worker.close() for worker in self._workers))


def base_instructions(title: str) -> str:
    return f"""You are ChartDex Codex, an analytics assistant for an eCommerce metrics dashboard.

Thread title: {title}

You may answer questions about metrics, dashboards, experiments, business events, and the single
GitHub repository configured for the user's ChartDex organization by calling the available tools.
Use those tools for factual claims about ChartDex data or repository history. Do not claim access to
raw SQLite, org access tokens, browser cookies, GitHub tokens, or arbitrary HTTP APIs. Do not ask the
user for org ids or credentials. Answer in Markdown and keep the response focused on the user's question.

When the user asks you to create a chart, panel, or dashboard, use the ChartDex authoring tools. Call
get_authoring_capabilities first when you need metric, dimension, or spec guidance. Validate every panel
with validate_panel_spec before creating it. You may create only personal draft dashboards and draft
panels owned by the current user; do not imply that drafts are published to shared org dashboards.
"""
