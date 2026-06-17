"""Scheduler output sanitization and summary extraction helpers."""

from __future__ import annotations

import os
from collections.abc import Sequence

from agent_runner import AgentResult
from config import SymphonyConfig

from .markers import (
    _ANSI_ESCAPE_RE,
    _bound_summary_block,
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
    for secret in secrets:
        if secret:
            summary = summary.replace(secret, _REDACTED)
    if is_block:
        summary = _bound_summary_block(summary)
    return summary


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
