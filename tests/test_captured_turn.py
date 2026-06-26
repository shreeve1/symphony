"""Tests for ADR-0022: post the agent's captured turn, not a forced summary block."""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from agent_runner import AgentResult

UTC = timezone.utc

# ---------------------------------------------------------------------------
# T.1.1 – Interactive/no-marker case: stdout has useful text but no
#         SYMPHONY_SUMMARY block → comment shows the natural turn.
# ---------------------------------------------------------------------------


def test_natural_turn_without_summary_marker() -> None:
    from scheduler.sanitize import _capture_natural_turn

    result = AgentResult(
        0, 10, False, stdout="Jellyfin CT106 healthy. HTTP 200, mounts OK."
    )
    summary = _capture_natural_turn(result, ())
    assert summary is not None
    assert "Jellyfin CT106 healthy" in summary
    assert "SYMPHONY_SUMMARY" not in summary


# ---------------------------------------------------------------------------
# T.1.2 – Artifact-delivery case: stdout has an inline prompt → comment shows
#         the prompt, not a description of it.
# ---------------------------------------------------------------------------


def test_natural_turn_inline_artifact() -> None:
    from scheduler.sanitize import _capture_natural_turn

    stdout = "Here is the generated plan:\n\n```yaml\nname: my-plan\nsteps: []\n```\n"
    result = AgentResult(0, 10, False, stdout=stdout)
    summary = _capture_natural_turn(result, ())
    assert summary is not None
    assert "name: my-plan" in summary
    assert "steps: []" in summary


# ---------------------------------------------------------------------------
# T.1.3 – Natural turn wins when both turn text and summary block present.
# ---------------------------------------------------------------------------


def test_natural_turn_wins_over_summary_block() -> None:
    from scheduler.sanitize import _capture_natural_turn

    stdout = (
        "chatter before\n"
        "SYMPHONY_SUMMARY_BEGIN\n"
        "## Override\n"
        "SYMPHONY_SUMMARY_END\n"
        "chatter after\n"
    )
    result = AgentResult(0, 10, False, stdout=stdout)
    summary = _capture_natural_turn(result, ())
    assert summary is not None
    # Full natural turn: chatter + block content (fences stripped).
    assert "chatter before" in summary
    assert "chatter after" in summary
    assert "## Override" in summary
    assert "SYMPHONY_SUMMARY_BEGIN" not in summary
    assert "SYMPHONY_SUMMARY_END" not in summary


# ---------------------------------------------------------------------------
# T.1.4 – Empty stdout falls back gracefully.
# ---------------------------------------------------------------------------


def test_empty_stdout_returns_none() -> None:
    from scheduler.sanitize import _capture_natural_turn

    assert _capture_natural_turn(AgentResult(0, 10, False, stdout=""), ()) is None
    assert _capture_natural_turn(AgentResult(0, 10, False, stdout="   "), ()) is None


def test_stdout_only_has_result_marker_returns_none() -> None:
    from scheduler.sanitize import _capture_natural_turn

    # Only protocol markers → stripped to empty → None.
    result = AgentResult(0, 10, False, stdout="SYMPHONY_RESULT: done\n")
    assert _capture_natural_turn(result, ()) is None


# ---------------------------------------------------------------------------
# T.1.5 – Secret redaction on full stream.
# ---------------------------------------------------------------------------


def test_secret_redaction_on_full_stream() -> None:
    from scheduler.sanitize import _capture_natural_turn

    token = "secret-token-abc123"
    result = AgentResult(
        0, 10, False, stdout=f"Debug: {token}\nAll good.\nSYMPHONY_RESULT: done"
    )
    summary = _capture_natural_turn(result, (token,))
    assert summary is not None
    assert token not in summary
    assert "***REDACTED***" in summary
    assert "All good." in summary
    assert "SYMPHONY_RESULT" not in summary


# ---------------------------------------------------------------------------
# T.1.6 – Display bound: turn exceeding DISPLAY_MAX_CHARS gets head+tail
#         truncated.
# ---------------------------------------------------------------------------


def test_display_bound_truncation() -> None:
    from scheduler.markers import DISPLAY_MAX_CHARS
    from scheduler.sanitize import _capture_natural_turn

    huge = "X" * (DISPLAY_MAX_CHARS + 1000)
    result = AgentResult(0, 10, False, stdout=huge)
    summary = _capture_natural_turn(result, (), is_coding=False)
    assert summary is not None
    assert len(summary) < DISPLAY_MAX_CHARS + 500  # smaller than raw input
    assert "truncated" in summary.lower()


# ---------------------------------------------------------------------------
# T.1.7 – Coding binding file-fallback: turn exceeds DISPLAY_MAX_CHARS on a
#         coding binding → file written, comment shows path + excerpt.
# ---------------------------------------------------------------------------


def test_coding_binding_file_fallback(tmp_path: Path) -> None:
    from scheduler.markers import DISPLAY_MAX_CHARS
    from scheduler.sanitize import _capture_natural_turn

    huge = "Y" * (DISPLAY_MAX_CHARS + 500)
    result = AgentResult(0, 10, False, stdout=huge)
    summary = _capture_natural_turn(
        result,
        (),
        is_coding=True,
        binding_name="test-binding",
        homelab_repo_path=str(tmp_path),
    )
    assert summary is not None
    # Should contain path reference and excerpt.
    assert ".symphony-runs" in summary
    assert "test-binding-" in summary
    assert ".md" in summary
    # The file should exist.
    run_dir = tmp_path / ".symphony-runs"
    files = list(run_dir.glob("test-binding-*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert huge in content


# ---------------------------------------------------------------------------
# T.1.8 – Claude transcript extraction: mock JSONL with tool_use/tool_result
#         blocks → extracted text strips them.
# ---------------------------------------------------------------------------


def test_extract_last_assistant_turn_strips_tool_blocks(tmp_path: Path) -> None:
    from claude_runner import _extract_last_assistant_turn

    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "user",
                "content": [{"type": "text", "text": "do something"}],
            }
        )
        + "\n"
        + json.dumps(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check that.\n"},
                    {"type": "tool_use", "name": "read", "id": "1"},
                    {"type": "tool_result", "content": "file contents"},
                    {"type": "text", "text": "Done."},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    turn = _extract_last_assistant_turn(transcript)
    assert turn is not None
    assert "Let me check that." in turn
    assert "Done." in turn
    assert "file contents" not in turn  # tool_result stripped


# ---------------------------------------------------------------------------
# T.1.9 – Claude missing transcript returns None.
# ---------------------------------------------------------------------------


def test_extract_last_assistant_turn_missing_file() -> None:
    from claude_runner import _extract_last_assistant_turn

    assert _extract_last_assistant_turn(Path("/nonexistent/transcript.jsonl")) is None


def test_extract_last_assistant_turn_empty_file(tmp_path: Path) -> None:
    from claude_runner import _extract_last_assistant_turn

    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("", encoding="utf-8")
    assert _extract_last_assistant_turn(transcript) is None


def test_extract_last_assistant_turn_no_assistant_text(tmp_path: Path) -> None:
    from claude_runner import _extract_last_assistant_turn

    transcript = tmp_path / "no_assistant.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": [{"type": "text", "text": "hello"}]})
        + "\n"
        + json.dumps(
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "bash", "id": "1"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # All assistant blocks are tool_use/tool_result → no text extracted.
    assert _extract_last_assistant_turn(transcript) is None


# ---------------------------------------------------------------------------
# T.1.10 – OUTPUT_CONTRACT no longer requires summary block.
# ---------------------------------------------------------------------------


def test_output_contract_does_not_require_summary_block() -> None:
    from prompt_renderer import OUTPUT_CONTRACT

    assert "optional" in OUTPUT_CONTRACT.lower()
    assert "override what gets posted" in OUTPUT_CONTRACT.lower()
    # Old mandatory language must be gone.
    assert "plus a summary block" not in OUTPUT_CONTRACT
    assert "For result outcomes, the summary block carries" not in OUTPUT_CONTRACT
