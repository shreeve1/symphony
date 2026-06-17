"""Scheduler output marker parsing helpers."""

from __future__ import annotations

import re
from typing import Any

# Matches CSI escape sequences (e.g. \x1b[0m, \x1b[90m, \x1b[1;31m).
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_RESULT_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_RESULT:[ \t]*(done|review|blocked)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_QUESTION_BLOCK_RE = re.compile(
    r"^SYMPHONY_QUESTION_BEGIN[ \t]*\n(.*?)\nSYMPHONY_QUESTION_END[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_SUMMARY_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_SUMMARY:[ \t]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_METRIC_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_(COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):[ \t]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_SUMMARY_BLOCK_RE = re.compile(
    r"^SYMPHONY_SUMMARY_BEGIN[ \t]*\n(.*?)\nSYMPHONY_SUMMARY_END[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_MARKER_LINE_RE = re.compile(
    r"^[ \t]*SYMPHONY_(?:RESULT|SUMMARY|COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):.*$",
    re.IGNORECASE | re.MULTILINE,
)
_QUESTION_MARKER_LINE_RE = re.compile(
    r"^SYMPHONY_QUESTION_(?:BEGIN|END)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_PERMISSION_GATE_RE = re.compile(
    r"permission requested:|auto-rejecting|user rejected permission",
    re.IGNORECASE,
)
_APPROVAL_GATE_RE = re.compile(
    r"awaiting explicit .*approval|requires explicit .*approval|cannot (?:proceed|execute|run).*without approval|destructive .*approval|(?<!no )\bapproval required\b(?!\s*:\s*(?:none|n/a|no)\b)",
    re.IGNORECASE,
)
SUMMARY_MAX_CHARS = 500
SUMMARY_BLOCK_MAX_CHARS = 4000
SUMMARY_BLOCK_HEAD_CHARS = 2500
SUMMARY_BLOCK_TAIL_CHARS = 1200


def _parse_result_marker(stdout: str) -> str | None:
    """Return the last SYMPHONY_RESULT verdict in stdout, or None."""

    if not stdout:
        return None
    matches = _RESULT_MARKER_RE.findall(stdout)
    if not matches:
        return None
    return matches[-1].lower()


def _parse_summary_marker(*streams: str) -> str | None:
    """Return the last SYMPHONY_SUMMARY line across the given streams, or None."""

    summary: str | None = None
    for stream in streams:
        if not stream:
            continue
        matches = _SUMMARY_MARKER_RE.findall(stream)
        if matches:
            summary = matches[-1]
    if summary is None:
        return None
    cleaned = _ANSI_ESCAPE_RE.sub("", summary).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return None
    if len(cleaned) > SUMMARY_MAX_CHARS:
        cleaned = cleaned[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return cleaned


def _bound_summary_block(text: str) -> str:
    """Bound a multi-line summary block, keeping head and tail on overflow."""

    if len(text) <= SUMMARY_BLOCK_MAX_CHARS:
        return text
    head = text[:SUMMARY_BLOCK_HEAD_CHARS].rstrip()
    tail = text[-SUMMARY_BLOCK_TAIL_CHARS:].lstrip()
    return (
        f"{head}\n\n"
        f"[Summary truncated from {len(text)} characters for comment readability.]\n\n"
        f"{tail}"
    )


def _parse_summary_block(*streams: str) -> str | None:
    """Return the last SYMPHONY_SUMMARY_BEGIN/END block across streams, or None."""

    block: str | None = None
    for stream in streams:
        if not stream:
            continue
        matches = _SUMMARY_BLOCK_RE.findall(stream)
        if matches:
            block = matches[-1]
    if block is None:
        return None
    cleaned = _ANSI_ESCAPE_RE.sub("", block)
    cleaned = _MARKER_LINE_RE.sub("", cleaned)
    cleaned = cleaned.strip("\n").strip()
    if not cleaned:
        return None
    return cleaned


def _parse_question_block(*streams: str) -> str | None:
    """Return the last SYMPHONY_QUESTION_BEGIN/END block across streams."""

    block: str | None = None
    for stream in streams:
        if not stream:
            continue
        matches = _QUESTION_BLOCK_RE.findall(stream)
        if matches:
            block = matches[-1]
    if block is None:
        return None
    cleaned = _ANSI_ESCAPE_RE.sub("", block)
    cleaned = _MARKER_LINE_RE.sub("", cleaned)
    cleaned = _QUESTION_MARKER_LINE_RE.sub("", cleaned)
    cleaned = cleaned.strip("\n").strip()
    if not cleaned:
        return None
    return cleaned


def _parse_run_metrics(stdout: str) -> dict[str, Any]:
    """Extract optional cost/token markers emitted by pi stdout."""

    metrics: dict[str, Any] = {}
    marker_map = {
        "COST_USD": "cost_usd",
        "INPUT_TOKENS": "input_tokens",
        "OUTPUT_TOKENS": "output_tokens",
    }
    for marker, raw_value in _METRIC_MARKER_RE.findall(stdout or ""):
        key = marker_map[marker.upper()]
        try:
            if key == "cost_usd":
                metrics[key] = float(raw_value.strip())
            else:
                metrics[key] = int(raw_value.strip())
        except ValueError:
            continue
    return metrics


def _hit_permission_gate(stdout: str, stderr: str) -> bool:
    """Return true when the executor clean-exited after denied tool access."""

    return bool(_PERMISSION_GATE_RE.search(f"{stdout}\n{stderr}"))


def _hit_approval_gate(stdout: str, stderr: str) -> bool:
    """Return true when a clean exit still needs operator approval."""

    return bool(_APPROVAL_GATE_RE.search(f"{stdout}\n{stderr}"))
