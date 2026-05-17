import json
from pathlib import Path

import anyio

from app.codex_agent import CodexAppServerAgent
from app.codex_tools import ChartDexToolContext


def test_codex_app_server_agent_handles_dynamic_tool_call(monkeypatch, tmp_path: Path) -> None:
    created_processes: list[FakeProcess] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        process = FakeProcess(limit=kwargs.get("limit"))
        created_processes.append(process)
        process.argv = args
        return process

    async def fake_handle_tool_call(context, namespace, tool, arguments):
        assert context.org_id == "org_acme"
        assert namespace == "chartdex"
        assert tool == "list_metrics"
        assert arguments == {}
        return '{"metrics":[]}'

    monkeypatch.setattr("app.codex_agent.asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("app.codex_agent.handle_tool_call", fake_handle_tool_call)
    agent = CodexAppServerAgent(command="codex space app-server", cwd=tmp_path)
    context = ChartDexToolContext(
        app_db_path=tmp_path / "app.sqlite3",
        org_id="org_acme",
        user_id="u_admin",
        thread_id="thread_1",
    )

    result = anyio.run(agent.run_thread, "Test", "Use a tool", context)

    assert result.external_thread_id == "external-thread-1"
    assert result.markdown == "Tool-backed answer"
    assert created_processes[0].argv == ("codex", "space", "app-server")
    sent = created_processes[0].stdin.messages
    assert [message["method"] for message in sent[:3]] == [
        "initialize",
        "thread/start",
        "turn/start",
    ]
    assert sent[1]["params"]["dynamicTools"][0]["namespace"] == "chartdex"
    assert any(tool["namespace"] == "github" for tool in sent[1]["params"]["dynamicTools"])
    assert sent[3]["result"] == {
        "contentItems": [{"type": "inputText", "text": '{"metrics":[]}'}],
        "success": True,
    }


class FakeStdin:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def write(self, data: bytes) -> None:
        self.messages.append(json.loads(data.decode()))

    async def drain(self) -> None:
        return None


class FakeStdout:
    def __init__(self) -> None:
        self._messages = [
            {"id": 1, "result": {"ok": True}},
            {"id": 2, "result": {"thread": {"id": "external-thread-1"}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {
                "method": "item/tool/call",
                "id": 0,
                "params": {
                    "threadId": "external-thread-1",
                    "turnId": "turn-1",
                    "callId": "call-1",
                    "namespace": "chartdex",
                    "tool": "list_metrics",
                    "arguments": {},
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {"threadId": "external-thread-1", "delta": "Tool-backed answer"},
            },
            {
                "method": "turn/completed",
                "params": {"threadId": "external-thread-1", "turn": {"status": "completed"}},
            },
        ]

    async def readline(self) -> bytes:
        return (json.dumps(self._messages.pop(0)) + "\n").encode()


class FakeStderr:
    async def read(self) -> bytes:
        return b""


class FakeProcess:
    def __init__(self, limit: int | None = None) -> None:
        self.stdin = FakeStdin()
        self.stdout = FakeStdout()
        self.stderr = FakeStderr()
        self.returncode = None
        self.limit = limit
        self.argv = ()

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = 1

    async def wait(self) -> int:
        return self.returncode or 0
