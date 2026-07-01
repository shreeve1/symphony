"""Scheduler output sanitization and summary extraction helpers."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Sequence
from pathlib import Path

from agent_runner import AgentResult
from config import SymphonyConfig

from .markers import (
    _ANSI_ESCAPE_RE,
    _bound_display,
    _bound_summary_block,
    DISPLAY_MAX_CHARS,
    _parse_question_block,
    _parse_summary_block,
    _parse_summary_marker,
)

REPORT_MAX_BYTES = 2048
STDERR_SUMMARY_MAX_LINES = 8
STDERR_SUMMARY_MAX_CHARS = 900
PREVIOUS_COMMENT_MAX_CHARS = 1500
PREVIOUS_COMMENT_TAIL_CHARS = 500
_REDACTED = "***REDACTED***"
_SECRET_ENV_KEYS = (
    "PLANE_API_KEY",
    "SYMPHONY_PLANE_API_KEY",
    "ZAI_API_KEY",
    "CLIP" + "ROXY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
)


def _sanitize_report(
    text: str, secrets: Sequence[str], *, max_bytes: int = REPORT_MAX_BYTES
) -> str:
    report = _ANSI_ESCAPE_RE.sub("", text).strip()
    for secret in secrets:
        if secret:
            report = report.replace(secret, _REDACTED)
    encoded = report.encode("utf-8", errors="replace")
    if len(encoded) > max_bytes:
        tail = encoded[-max_bytes:].decode("utf-8", errors="replace")
        report = "... [output truncated]\n\n" + tail
    return report


def _collect_secrets(config: SymphonyConfig) -> list[str]:
    secrets: list[str] = []
    if config.plane_api_key:
        secrets.append(config.plane_api_key)
    if config.telegram_bot_token:
        secrets.append(config.telegram_bot_token)
    for key in _SECRET_ENV_KEYS:
        val = os.environ.get(key, "")
        if val and val not in secrets:
            secrets.append(val)
    return secrets


def _format_report(result: AgentResult, secrets: Sequence[str]) -> tuple[str, str]:
    stdout = _sanitize_report(result.stdout, secrets)
    stderr = _sanitize_report(result.stderr, secrets)
    return stdout, stderr


def _format_stderr_summary(stderr: str) -> str:
    """Return a bounded, human-readable stderr summary for Plane comments."""

    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return ""
    selected = lines[-STDERR_SUMMARY_MAX_LINES:]
    body = "\n".join(f"- {line}" for line in selected)
    if len(body) > STDERR_SUMMARY_MAX_CHARS:
        body = body[: STDERR_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    omitted = len(lines) - len(selected)
    prefix = "**Stderr summary:**"
    if omitted > 0:
        prefix += f" last {len(selected)} non-empty lines shown; {omitted} earlier lines omitted."
    return f"{prefix}\n{body}"


def _format_previous_comment_body(body: str) -> str:
    """Bound prior Plane comments before injecting them into the next prompt."""

    stripped = body.strip()
    if len(stripped) <= PREVIOUS_COMMENT_MAX_CHARS:
        return stripped
    first_line = next(
        (line.strip() for line in stripped.splitlines() if line.strip()),
        "Previous comment",
    )
    if len(first_line) > 180:
        first_line = first_line[:179].rstrip() + "…"
    tail = stripped[-PREVIOUS_COMMENT_TAIL_CHARS:].strip()
    return (
        f"{first_line}\n\n"
        f"[Previous comment truncated from {len(stripped)} characters for Symphony prompt readability.]\n\n"
        f"{tail}"
    )


def _redact_stream(text: str, secrets: Sequence[str]) -> str:
    """Apply secret redaction to any text (standalone, pulled from _extract_summary)."""

    for secret in secrets:
        if secret:
            text = text.replace(secret, _REDACTED)
    return text


def _extract_summary(
    result: AgentResult, secrets: Sequence[str], *, include_stderr: bool = True
) -> str | None:
    """Pull SYMPHONY_SUMMARY from raw streams and apply secret redaction."""

    streams = (result.stdout, result.stderr) if include_stderr else (result.stdout,)
    summary = _parse_summary_block(*streams)
    is_block = summary is not None
    if summary is None:
        summary = _parse_summary_marker(*streams)
    if summary is None:
        return None
    summary = _redact_stream(summary, secrets)
    if is_block:
        summary = _bound_summary_block(summary)
    return summary


def _capture_natural_turn(
    result: AgentResult,
    secrets: Sequence[str],
    *,
    scheduling: bool = True,
    is_claude: bool = False,
    binding_name: str = "",
    homelab_repo_path: str = "",
) -> str | None:
    """Return the agent's natural turn as the comment body.

    pi bindings: result.stdout is already the captured turn.
    claude bindings: result.stdout may be ``<natural_turn>\n\n---\n<result_file>``
    (see _extract_last_assistant_turn wiring in claude_runner.py).

    Redacts secrets and display-bounds the turn. For bindings without the
    scheduling capability (coding bindings) on overflow, writes the full turn
    to a file and returns ``path + excerpt``.
    Returns ``None`` when stdout is empty (caller should fall back to
    _extract_summary).
    """

    stdout = (result.stdout or "").strip()
    if not stdout:
        return None

    # ponytail: claude prepends natural turn with a "\n\n---\n" separator;
    # use only the natural turn part for the comment. This is claude-only wiring:
    # a pi agent's own Markdown ``---`` horizontal rule must NOT be treated as a
    # turn separator (that truncated issue 168's answer to its preamble).
    if is_claude:
        separator_idx = stdout.find("\n\n---\n")
        if separator_idx >= 0:
            stdout = stdout[:separator_idx].strip() or stdout

    # Strip ANSI escapes and all SYMPHONY_ marker lines (RESULT, SCHEDULE,
    # COST_USD, INPUT_TOKENS, OUTPUT_TOKENS) — these are protocol, not prose.
    cleaned = _ANSI_ESCAPE_RE.sub("", stdout)
    cleaned = re.sub(
        r"^[ \t]*SYMPHONY_(?:RESULT|SCHEDULE|COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):.*$",
        "",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Strip SUMMARY_BEGIN/END fences; keep content between them.
    cleaned = cleaned.replace("SYMPHONY_SUMMARY_BEGIN", "").replace(
        "SYMPHONY_SUMMARY_END", ""
    )
    # Strip SYMPHONY_SUMMARY: prefix from lines; keep the content.
    cleaned = re.sub(
        r"^[ \t]*SYMPHONY_SUMMARY:[ \t]*",
        "",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Strip QUESTION_BEGIN/END fences.
    cleaned = cleaned.replace("SYMPHONY_QUESTION_BEGIN", "").replace(
        "SYMPHONY_QUESTION_END", ""
    )
    # Collapse multiple blank lines from stripped markers.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = cleaned.strip()
    if not cleaned:
        return None

    text = _redact_stream(cleaned, secrets)

    if len(text) <= DISPLAY_MAX_CHARS:
        return text

    excerpt = _bound_display(text)
    if scheduling:
        return excerpt

    # ponytail: file-fallback for coding bindings — write full turn to
    # .symphony-runs/<binding>-<timestamp>.md, return path + excerpt.
    # Agent owns its own git; no Symphony landing step required.
    repo_dir = Path(homelab_repo_path or ".")
    run_dir = repo_dir / ".symphony-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    safe_name = binding_name.replace("/", "-").replace(" ", "-") or "run"
    out_file = run_dir / f"{safe_name}-{int(time.time())}.md"
    out_file.write_text(text, encoding="utf-8")
    return f"[{out_file.name}]({out_file.relative_to(repo_dir)})\n\n{excerpt}"


def _extract_question(
    result: AgentResult, secrets: Sequence[str], *, include_stderr: bool = True
) -> str | None:
    """Pull SYMPHONY_QUESTION from raw streams and apply secret redaction."""

    streams = (result.stdout, result.stderr) if include_stderr else (result.stdout,)
    question = _parse_question_block(*streams)
    if question is None:
        return None
    for secret in secrets:
        if secret:
            question = question.replace(secret, _REDACTED)
    return _bound_summary_block(question)
