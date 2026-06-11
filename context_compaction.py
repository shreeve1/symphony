"""Engine-owned Podium Issue Context compaction."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent_runner import AgentResult


DEFAULT_CONTEXT_COMPACT_THRESHOLD_TOKENS = 16_000
DEFAULT_CONTEXT_COMPACT_KEEP_RECENT_RUNS = 3
COMPACTED_CONTEXT_MARKER = "SYMPHONY_COMPACTED_CONTEXT:"

COMPACTION_PROMPT = f"""
You are compacting Symphony Podium Issue Context before an operator Run.

Goals:
- Summarize Runs older than {{keep_recent_runs}} recent Runs.
- Preserve the last {{keep_recent_runs}} Runs verbatim.
- Preserve operator-edited instruction blocks verbatim.
- Preserve durable decisions, blockers, accepted terminology, and next-step constraints.
- Remove duplicated logs, repeated stack traces, and obsolete transient chatter.

Return exactly one marker followed by the compacted context:
{COMPACTED_CONTEXT_MARKER}
<compacted markdown>
""".strip()


class ContextCompactionError(RuntimeError):
    """Raised when context compaction cannot safely produce replacement text."""


def estimate_tokens(text: str) -> int:
    """Cheap v1 token estimate. Accurate enough for threshold decisions."""

    return len(text) // 4


def maybe_compact(
    issue: Any,
    binding: Any,
    agent_runner: Callable[[Any, str], AgentResult],
    *,
    threshold_tokens: int = DEFAULT_CONTEXT_COMPACT_THRESHOLD_TOKENS,
    keep_recent_runs: int = DEFAULT_CONTEXT_COMPACT_KEEP_RECENT_RUNS,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """Return issue context, compacted when it exceeds the configured threshold.

    The caller owns persistence. On agent failure or malformed output this raises,
    leaving the caller's stored ``context_md`` untouched.
    """

    context = str(getattr(issue, "context_md", "") or "")
    original_tokens = estimate_tokens(context)
    if original_tokens <= threshold_tokens:
        return context

    prompt = _build_prompt(
        context,
        binding_name=str(getattr(binding, "name", "") or ""),
        keep_recent_runs=keep_recent_runs,
        original_tokens=original_tokens,
    )
    result = agent_runner(issue, prompt)
    if result.timed_out:
        raise ContextCompactionError("context compaction agent timed out")
    if result.exit_code != 0:
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise ContextCompactionError(
            f"context compaction agent failed with exit code {result.exit_code}{suffix}"
        )

    compacted = parse_compacted_context(result.stdout)
    compacted_tokens = estimate_tokens(compacted)
    timestamp = now().isoformat()
    marker = (
        f"<!-- context compacted on {timestamp}, "
        f"trimmed {original_tokens}→{compacted_tokens} tokens -->"
    )
    return f"{marker}\n{compacted}"


def parse_compacted_context(output: str) -> str:
    """Extract compacted markdown after ``SYMPHONY_COMPACTED_CONTEXT:``."""

    marker_index = output.find(COMPACTED_CONTEXT_MARKER)
    if marker_index < 0:
        raise ContextCompactionError("context compaction output missing marker")
    compacted = output[marker_index + len(COMPACTED_CONTEXT_MARKER) :].strip()
    compacted = _strip_markdown_fence(compacted)
    if not compacted:
        raise ContextCompactionError("context compaction output was empty")
    return compacted


def _build_prompt(
    context: str,
    *,
    binding_name: str,
    keep_recent_runs: int,
    original_tokens: int,
) -> str:
    header = COMPACTION_PROMPT.format(keep_recent_runs=keep_recent_runs)
    return (
        f"{header}\n\n"
        f"Binding: {binding_name or 'unknown'}\n"
        f"Estimated tokens: {original_tokens}\n"
        f"Keep recent Runs verbatim: {keep_recent_runs}\n\n"
        "<issue_context>\n"
        f"{context}\n"
        "</issue_context>"
    )


def _strip_markdown_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text.strip()
