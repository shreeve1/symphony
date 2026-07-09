from __future__ import annotations

from agent_runner import AgentResult
from scheduler.run_records import _run_metrics


def test_run_metrics_prefers_rpc_usage() -> None:
    """When pi RPC usage is present, it wins and maps to run columns; zero
    fields are dropped so a partial update never clobbers with 0 (issue #343)."""
    result = AgentResult(
        0,
        10,
        False,
        stdout="SYMPHONY_INPUT_TOKENS: 999\n",  # markers ignored when usage set
        usage={
            "input_tokens": 1500,
            "output_tokens": 50,
            "cache_read_tokens": 1200,
            "cost_usd": 0.015,
        },
    )
    assert _run_metrics(result) == {
        "input_tokens": 1500,
        "output_tokens": 50,
        "cache_read_tokens": 1200,
        "cost_usd": 0.015,
    }


def test_run_metrics_drops_zero_usage_fields() -> None:
    result = AgentResult(
        0, 10, False, usage={"input_tokens": 800, "output_tokens": 0, "cost_usd": 0.0}
    )
    assert _run_metrics(result) == {"input_tokens": 800}


def test_run_metrics_falls_back_to_stdout_markers() -> None:
    """Non-RPC agents (print-mode pi, Claude) still report via SYMPHONY_*."""
    result = AgentResult(
        0,
        10,
        False,
        stdout=(
            "SYMPHONY_COST_USD: 0.0123\n"
            "SYMPHONY_INPUT_TOKENS: 123\n"
            "SYMPHONY_OUTPUT_TOKENS: 45\n"
        ),
        usage=None,
    )
    assert _run_metrics(result) == {
        "cost_usd": 0.0123,
        "input_tokens": 123,
        "output_tokens": 45,
    }
