from app.codex_agent import base_instructions
from app.codex_service import (
    build_follow_up_codex_prompt,
    build_initial_codex_prompt,
    build_recovered_thread_prompt,
    is_missing_external_thread_error,
)
from app.codex_agent import CodexAgentError


def test_initial_codex_prompt_does_not_force_every_message_into_analytics() -> None:
    prompt = build_initial_codex_prompt(
        "This is a test",
        {"dashboard_id": "dash_revenue_overview"},
    )

    assert "User message:\nThis is a test" in prompt
    assert "Only treat this as an analytics investigation if the user asks" in prompt
    assert "smoke tests" in prompt
    assert "without calling tools" in prompt
    assert "User analytics question" not in prompt


def test_follow_up_codex_prompt_allows_direct_non_analytics_replies() -> None:
    prompt = build_follow_up_codex_prompt("thanks")

    assert "Follow-up message:\nthanks" in prompt
    assert "Continue the existing ChartDex investigation only if this message asks" in prompt
    assert "other non-analytics messages" in prompt


def test_base_instructions_do_not_treat_context_as_investigation_request() -> None:
    instructions = base_instructions("This is a test")

    assert "Do not assume that a dashboard context snapshot means" in instructions
    assert "answer" in instructions
    assert "directly and briefly without calling ChartDex tools" in instructions


def test_recovered_thread_prompt_includes_persisted_history() -> None:
    prompt = build_recovered_thread_prompt(
        {
            "turns": [
                {"role": "user", "markdown": "Why did conversion dip?"},
                {"role": "assistant", "markdown": "It appears related to Android."},
                {"role": "user", "markdown": "Break it down by campaign."},
                {"role": "assistant", "markdown": ""},
            ],
        },
        "Break it down by campaign.",
    )

    assert "previous external Codex app-server thread is unavailable" in prompt
    assert "USER:\nWhy did conversion dip?" in prompt
    assert "ASSISTANT:\nIt appears related to Android." in prompt
    assert "Follow-up message:\nBreak it down by campaign." in prompt


def test_missing_external_thread_error_detection() -> None:
    assert is_missing_external_thread_error(
        CodexAgentError("Codex app-server request failed: {'message': 'thread not found: abc'}")
    )
    assert not is_missing_external_thread_error(CodexAgentError("Timed out waiting for Codex app-server"))
