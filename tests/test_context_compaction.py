from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module

import pytest

from agent_runner import AgentResult

compaction = import_module("context_compaction")
COMPACTED_CONTEXT_MARKER = vars(compaction)["COMPACTED_CONTEXT_MARKER"]
COMPACTION_PROMPT = vars(compaction)["COMPACTION_PROMPT"]
ContextCompactionError = vars(compaction)["ContextCompactionError"]
estimate_tokens = vars(compaction)["estimate_tokens"]
maybe_compact = vars(compaction)["maybe_compact"]
parse_compacted_context = vars(compaction)["parse_compacted_context"]


@dataclass(frozen=True)
class Issue:
    id: str = "1"
    context_md: str = ""


@dataclass(frozen=True)
class Binding:
    name: str = "trading"
    default_agent: str = "pi"


def test_below_threshold_noops_without_invoking_agent() -> None:
    calls = 0

    def agent_runner(issue, prompt: str) -> AgentResult:
        nonlocal calls
        calls += 1
        return AgentResult(0, 1, False, stdout="", stderr="")

    assert maybe_compact(
        Issue(context_md="short"),
        Binding(),
        agent_runner,
        threshold_tokens=estimate_tokens("short") + 1,
    ) == "short"
    assert calls == 0


def test_above_threshold_invokes_agent_and_adds_marker() -> None:
    seen_prompt = ""

    def agent_runner(issue, prompt: str) -> AgentResult:
        nonlocal seen_prompt
        seen_prompt = prompt
        return AgentResult(
            0,
            1,
            False,
            stdout=f"{COMPACTED_CONTEXT_MARKER}\ncompact result",
            stderr="",
        )

    result = maybe_compact(
        Issue(context_md="x" * 20),
        Binding(),
        agent_runner,
        threshold_tokens=1,
        keep_recent_runs=2,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )

    assert seen_prompt.startswith(COMPACTION_PROMPT.format(keep_recent_runs=2))
    assert "Preserve the last 2 Runs verbatim" in seen_prompt
    assert "operator-edited instruction blocks" in seen_prompt
    assert result.startswith(
        "<!-- context compacted on 2026-06-11T00:00:00+00:00, trimmed 5→3 tokens -->"
    )
    assert result.endswith("compact result")


@pytest.mark.parametrize(
    "agent_result",
    [
        AgentResult(1, 1, False, stdout="", stderr="boom"),
        AgentResult(0, 1, True, stdout="", stderr=""),
    ],
)
def test_agent_error_raises_without_replacement(agent_result: AgentResult) -> None:
    def agent_runner(issue, prompt: str) -> AgentResult:
        return agent_result

    with pytest.raises(ContextCompactionError):
        maybe_compact(
            Issue(context_md="x" * 20),
            Binding(),
            agent_runner,
            threshold_tokens=1,
        )


def test_missing_marker_raises() -> None:
    with pytest.raises(ContextCompactionError):
        parse_compacted_context("no marker here")
