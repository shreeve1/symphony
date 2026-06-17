"""Core Symphony scheduler loop."""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from agent_runner import AgentAdapter, AgentResult
from blocked_reconciler import reconcile_blocked
from claude_runner import claude_probe_failure_reason
from code_version import resolve_code_sha
from config import ProjectBinding, SymphonyConfig
from context_compaction import ContextCompactionError, estimate_tokens, maybe_compact
from model_catalog import load_models, resolve_model
from repo_host import repo_host_for
from notifier import (
    TelegramNotifier,
    format_blocked_message,
    format_review_message,
)
from plane_adapter import PlaneRateLimitError
from tracker_adapter import TrackerAdapter
from tracker_types import (
    CandidateIssue,
    CommentPayload,
    _extract_labels,
    _is_state,
    _candidate_from_issue,
    _parse_iso,
)
from prompt_renderer import render_previous_comments_block
from session_continuity import (
    ACTION_RESUME,
    REASON_SESSION_ABSENT,
    ResumeDecision,
    derive_session_id,
    evaluate_resume_eligibility,
)
from schedule import (
    CandidateComment,
    ScheduleEvent,
    ScheduleEventType,
    ScheduleParseError,
    latest_event,
)
from tracker_contract import DEFAULT_CONTRACT, TrackerContract, TrackerRole
from web.api.db import resolve_run_log_root

_wake_signal = import_module("web.api.wake_signal")
consume_wake_sentinel = _wake_signal.consume_wake_sentinel


LOGGER = logging.getLogger(__name__)
# Legacy claim-time fallback: kept so ``_claimed_at`` can still parse claim
# timestamps from comments on adapters without a Run store (Plane) and from
# historical issues. New claim time comes from the Run record's ``started_at``.
CLAIM_PREFIX = "Symphony claimed at "
REPORT_MAX_BYTES = 2048
# The on-disk run log keeps far more than the 2 KB comment/context bound so the
# run-detail pane can show full output; still capped (tail-kept) so a runaway
# agent cannot grow the run-log dir without limit.
LOG_MAX_BYTES = 1_048_576
STDERR_SUMMARY_MAX_LINES = 8
STDERR_SUMMARY_MAX_CHARS = 900
PREVIOUS_COMMENT_MAX_CHARS = 1500
PREVIOUS_COMMENT_TAIL_CHARS = 500
# Matches CSI escape sequences (e.g. \x1b[0m, \x1b[90m, \x1b[1;31m). Stripped
# from agent stderr so failure comments are readable on Plane, which renders
# fenced code as plain text.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
SCHEDULED_RELEASE_PAGE_SIZE = 50
SCHEDULED_RELEASE_MAX_PAGES_PER_TICK = 3
RATE_LIMIT_BASE_COOLDOWN_S = 30.0
RATE_LIMIT_MAX_COOLDOWN_S = 300.0
RATE_LIMIT_JITTER_FRACTION = 0.2
LOG_RETENTION_INTERVAL = timedelta(hours=24)
WAKE_SENTINEL_CHECK_INTERVAL_S = 1.0

SCHEDULED_LABEL_WINDOW_TZ = ZoneInfo("America/Los_Angeles")
SCHEDULED_LABEL_WINDOW_START_HOUR = 0
SCHEDULED_LABEL_WINDOW_END_HOUR = 6
SCHEDULED_LABEL_DEFAULT_REASON = "scheduled label maintenance window"
SCHEDULED_LABEL_DEFAULT_SOURCE = "scheduled label maintenance window (12am-6am PT)"
_REDACTED = "***REDACTED***"


@dataclass
class _DispatchState:
    """Per-binding dispatch state — isolates concurrency from module globals.

    Created by ``run_loop`` for each binding so that semaphore cap, in-flight
    tracking, and poll interval are scoped to one project rather than shared
    across all bindings. Direct ``run_tick`` / ``_dispatch_one`` calls create
    or receive an explicit ``_DispatchState`` so tests and production exercise
    the same state path.

    **Concurrency multiplication:** each binding gets its own semaphore of size
    ``run_cap``, so total host-wide concurrent runs is ``run_cap × num_bindings``.
    Operators must size ``run_cap`` accordingly — the cap is per-project, not
    per-host.
    """

    semaphore: asyncio.Semaphore
    in_flight_ids: set[str]
    in_flight_lock: asyncio.Lock
    poll_interval: float
    cooldown_until: datetime | None = None
    cooldown_attempts: int = 0
    pending_review_issue_ids: set[str] = field(default_factory=set)
    pending_completion_bodies: dict[str, str] = field(default_factory=dict)


def _new_dispatch_state(config: SymphonyConfig) -> _DispatchState:
    return _DispatchState(
        semaphore=asyncio.Semaphore(config.run_cap),
        in_flight_ids=set(),
        in_flight_lock=asyncio.Lock(),
        poll_interval=config.poll_interval_ms / 1000,
    )


def _cooldown_remaining_s(
    state: _DispatchState,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> float:
    if state.cooldown_until is None:
        return 0.0
    remaining = (state.cooldown_until - now()).total_seconds()
    if remaining <= 0:
        state.cooldown_until = None
        return 0.0
    return remaining


def _record_rate_limit(
    state: _DispatchState,
    exc: PlaneRateLimitError,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    jitter: Callable[[], float] = random.random,
) -> None:
    state.cooldown_attempts += 1
    if exc.retry_after_s is not None:
        delay_s = exc.retry_after_s
        delay_s += max(1.0, delay_s * RATE_LIMIT_JITTER_FRACTION) * jitter()
    else:
        delay_s = min(
            RATE_LIMIT_MAX_COOLDOWN_S,
            RATE_LIMIT_BASE_COOLDOWN_S * (2 ** max(0, state.cooldown_attempts - 1)),
        )
        delay_s += delay_s * RATE_LIMIT_JITTER_FRACTION * jitter()
    state.cooldown_until = now() + timedelta(seconds=delay_s)
    LOGGER.warning(
        "plane_rate_limited cooldown_s=%.3f attempts=%s",
        delay_s,
        state.cooldown_attempts,
    )


def _clear_rate_limit(state: _DispatchState) -> None:
    state.cooldown_until = None
    state.cooldown_attempts = 0


def _fixed_now(value: datetime) -> Callable[[], datetime]:
    def now() -> datetime:
        return value

    return now


# SYMPHONY_RESULT marker: agents may emit `SYMPHONY_RESULT: done|review|blocked`
# on its own line in stdout to declare an explicit verdict. Last occurrence wins,
# case-insensitive. Unknown values fall through to the heuristic.
_RESULT_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_RESULT:[ \t]*(done|review|blocked)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
# SYMPHONY_QUESTION_BEGIN/END block: agents use this instead of SYMPHONY_RESULT
# when deliberately parking a Run for operator clarification. Markers must sit at
# the start of a line so echoed contract examples remain inert.
_QUESTION_BLOCK_RE = re.compile(
    r"^SYMPHONY_QUESTION_BEGIN[ \t]*\n(.*?)\nSYMPHONY_QUESTION_END[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
# SYMPHONY_SUMMARY marker: agents may emit `SYMPHONY_SUMMARY: <one short line>`
# on its own line in stdout (or stderr — both are checked) to provide a
# human-readable result line for the Plane completion comment. Last occurrence
# wins, case-insensitive on the prefix. The captured text is trimmed to
# SUMMARY_MAX_CHARS and stripped of newlines so a misbehaving agent cannot
# dump the world into a Plane comment via this channel.
_SUMMARY_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_SUMMARY:[ \t]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_METRIC_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_(COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):[ \t]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
SUMMARY_MAX_CHARS = 500
# SYMPHONY_SUMMARY_BEGIN/END block: agents emit their full natural end-of-turn
# summary (markdown, multi-line) between these markers. Posted verbatim as the
# terminal-state comment. Bounded so a runaway agent cannot dump its whole
# transcript into the comment stream (comments are re-injected into the next
# prompt as untrusted context).
# Markers must sit at the start of a line (no leading whitespace). This keeps
# the indented example inside OUTPUT_CONTRACT from matching even when an agent
# echoes the prompt into its output stream — the echo stays indented.
_SUMMARY_BLOCK_RE = re.compile(
    r"^SYMPHONY_SUMMARY_BEGIN[ \t]*\n(.*?)\nSYMPHONY_SUMMARY_END[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
# Machine marker lines stripped from a summary block before display so they
# never surface in the human comment.
_MARKER_LINE_RE = re.compile(
    r"^[ \t]*SYMPHONY_(?:RESULT|SUMMARY|COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):.*$",
    re.IGNORECASE | re.MULTILINE,
)
_QUESTION_MARKER_LINE_RE = re.compile(
    r"^SYMPHONY_QUESTION_(?:BEGIN|END)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
SUMMARY_BLOCK_MAX_CHARS = 4000
SUMMARY_BLOCK_HEAD_CHARS = 2500
SUMMARY_BLOCK_TAIL_CHARS = 1200
# Cap the blocked-reason text sent to the Telegram notifier, leaving headroom
# under Telegram's 4096-char limit for the name/identifier/URL wrapping.
NOTIFY_REASON_MAX_CHARS = 2000
_PERMISSION_GATE_RE = re.compile(
    r"permission requested:|auto-rejecting|user rejected permission",
    re.IGNORECASE,
)
_APPROVAL_GATE_RE = re.compile(
    r"awaiting explicit .*approval|requires explicit .*approval|cannot (?:proceed|execute|run).*without approval|destructive .*approval|(?<!no )\bapproval required\b(?!\s*:\s*(?:none|n/a|no)\b)",
    re.IGNORECASE,
)


def _parse_result_marker(stdout: str) -> str | None:
    """Return the last SYMPHONY_RESULT verdict in stdout, or None."""

    if not stdout:
        return None
    matches = _RESULT_MARKER_RE.findall(stdout)
    if not matches:
        return None
    return matches[-1].lower()


def _parse_summary_marker(*streams: str) -> str | None:
    """Return the last SYMPHONY_SUMMARY line across the given streams, or None.

    Streams are searched in order; later streams override earlier ones, and
    within a stream the last occurrence wins. The captured text is collapsed
    to a single line, ANSI-stripped, and truncated to SUMMARY_MAX_CHARS so a
    runaway agent cannot smuggle a long block into a completion comment.
    """

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
    # Defensive: collapse whitespace/newlines a multiline regex shouldn't have
    # matched anyway, in case future regex tweaks loosen this.
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
    """Return the last SYMPHONY_SUMMARY_BEGIN/END block across streams, or None.

    Markdown and newlines are preserved (unlike the single-line marker). ANSI is
    stripped, machine marker lines are removed, and the result is bounded by
    ``_bound_summary_block`` so a runaway agent cannot smuggle its whole
    transcript into a completion comment.
    """

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
    # Return unbounded: bounding happens in _extract_summary *after* secret
    # redaction so a secret straddling the truncation boundary cannot leak a
    # surviving fragment.
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


class SchedulerError(RuntimeError):
    """Raised for scheduler setup failures."""


class SchedulerContextCompactionError(RuntimeError):
    """Raised when pre-dispatch context compaction fails safely."""


def _sanitize_report(
    text: str, secrets: Sequence[str], *, max_bytes: int = REPORT_MAX_BYTES
) -> str:
    report = _ANSI_ESCAPE_RE.sub("", text).strip()
    for secret in secrets:
        if secret:
            report = report.replace(secret, _REDACTED)
    encoded = report.encode("utf-8", errors="replace")
    if len(encoded) > max_bytes:
        # Keep the tail: failure context (final error, traceback footer) is
        # almost always more useful than the head of a long pi trace.
        tail = encoded[-max_bytes:].decode("utf-8", errors="replace")
        report = "... [output truncated]\n\n" + tail
    return report


_SECRET_ENV_KEYS = (
    "PLANE_API_KEY",
    "SYMPHONY_PLANE_API_KEY",
    "ZAI_API_KEY",
    "CLIP" + "ROXY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
)


def _collect_secrets(config: SymphonyConfig) -> list[str]:
    import os as _os

    secrets: list[str] = []
    if config.plane_api_key:
        secrets.append(config.plane_api_key)
    if config.telegram_bot_token:
        secrets.append(config.telegram_bot_token)
    for key in _SECRET_ENV_KEYS:
        val = _os.environ.get(key, "")
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
    """Pull SYMPHONY_SUMMARY from raw streams and apply secret redaction.

    Summary extraction runs against the *unsanitized* stdout/stderr because
    `_sanitize_report` keeps only the last 2 KB of stderr (for failure-comment
    bounding); a summary line earlier in the stream would otherwise be lost.
    Claude pane stderr echoes the prompt, so callers can restrict parsing to
    stdout only for Claude runs.
    """

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
    # Bound the (already-redacted) multi-line block. The single-line marker is
    # already capped at SUMMARY_MAX_CHARS, so it is left as-is.
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


def _write_run_log(log_path: Path, stdout: str, stderr: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"## stdout\n\n{stdout}\n\n## stderr\n\n{stderr}\n",
        encoding="utf-8",
    )


def _binding_from_config(config: SymphonyConfig) -> ProjectBinding | None:
    if len(config.bindings) == 1:
        return config.bindings[0]
    return None


def _binding_for_issue(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None = None,
) -> ProjectBinding | None:
    if binding is not None:
        return binding
    candidate_binding_name = getattr(candidate, "binding_name", "")
    if candidate_binding_name:
        for configured_binding in config.bindings:
            if configured_binding.name == candidate_binding_name:
                return configured_binding
    return _binding_from_config(config)


def _worktree_run_fields(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    base_branch: str,
    *,
    binding: ProjectBinding | None = None,
) -> dict[str, str]:
    if not getattr(candidate, "worktree_active", False):
        return {}
    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    if resolved_binding is not None and resolved_binding.is_remote:
        # Worktrees are disabled for remote bindings (ADR-0012): the remote
        # agent runs directly in binding.repo_path. Return no worktree fields so
        # no local git/Path op is driven against the remote path.
        return {}
    worktree_helpers = import_module("worktree_facade")
    branch_name = worktree_helpers.branch_name
    worktree_dir = worktree_helpers.worktree_dir

    binding_name = getattr(candidate, "binding_name", "") or (
        resolved_binding.name if resolved_binding is not None else ""
    )
    issue_id = str(candidate.id)
    return {
        "worktree_path": str(
            worktree_dir(config.homelab_repo_path, binding_name, issue_id)
        ),
        "branch_name": branch_name(binding_name, issue_id),
        "base_branch": base_branch,
    }


def _invoke_renderer(
    render_prompt: Callable[..., str],
    candidate: CandidateIssue,
    *,
    resume: bool = False,
) -> str:
    """Call the configured prompt renderer, passing resume when supported."""

    try:
        signature = inspect.signature(render_prompt)
    except (TypeError, ValueError):
        return render_prompt(candidate)
    if "resume" in signature.parameters:
        return render_prompt(candidate, resume=resume)
    return render_prompt(candidate)


def _dispatch_cwd(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None = None,
) -> Path:
    base_branch = getattr(candidate, "base_branch", "") or config.base_branch
    worktree_fields = _worktree_run_fields(
        config,
        candidate,
        base_branch,
        binding=binding,
    )
    if worktree_fields.get("worktree_path"):
        return Path(worktree_fields["worktree_path"])
    return config.homelab_repo_path


async def _prepare_resume_candidate(
    adapter: TrackerAdapter,
    config: SymphonyConfig,
    candidate: CandidateIssue,
    fresh_issue: dict[str, Any],
    *,
    binding: ProjectBinding | None = None,
) -> tuple[CandidateIssue, ResumeDecision | None]:
    """Annotate a candidate with Session Resume fields for resumable dispatch."""

    agent = binding.resolve_agent(candidate.labels) if binding is not None else "pi"
    session_id = derive_session_id(candidate.id)
    current_cwd = _dispatch_cwd(config, candidate, binding=binding)
    current_sha = (
        repo_host_for(binding, cwd=current_cwd).code_sha()
        if binding is not None
        else resolve_code_sha(current_cwd)
    )
    base_candidate = replace(
        candidate,
        agent_session_id=session_id,
        agent_session_sha=current_sha,
        resumed=False,
    )
    supports_resume = agent == "claude" or (
        agent == "pi" and getattr(binding, "pi_mode", "one-shot") == "rpc"
    )
    if (
        binding is None
        or not supports_resume
        or not getattr(adapter, "stores_context", False)
    ):
        return base_candidate, None

    latest_run_id = str(fresh_issue.get("latest_run_id") or "")
    get_run = getattr(adapter, "get_run", None)
    previous_run = None
    if latest_run_id and callable(get_run):
        previous_run = await _maybe_await(get_run(latest_run_id))
    if not previous_run:
        decision = ResumeDecision(
            action="refeed",
            reason=REASON_SESSION_ABSENT,
            session_id=session_id,
            session_file=Path(""),
        )
    else:
        previous_cwd = previous_run.get("worktree_path") or current_cwd
        decision = evaluate_resume_eligibility(
            previous_agent_kind=str(previous_run.get("agent") or ""),
            current_agent_kind=agent,
            previous_cwd=previous_cwd,
            current_cwd=current_cwd,
            session_id=session_id,
            agent_session_sha=previous_run.get("agent_session_sha"),
            current_git_sha=current_sha,
        )
    if decision.action == ACTION_RESUME:
        LOGGER.info(
            "resume_selected issue_id=%s session_id=%s session_file=%s",
            candidate.id,
            decision.session_id,
            decision.session_file,
        )
        return replace(base_candidate, resumed=True), decision
    LOGGER.info(
        "resume_skipped issue_id=%s reason=%s session_id=%s fell_back=true",
        candidate.id,
        decision.reason,
        decision.session_id,
    )
    return base_candidate, decision


async def _render_for_dispatch(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    render_prompt: Callable[..., str],
    agent_runner: Callable[..., AgentResult],
    *,
    now: Callable[[], datetime],
    binding: ProjectBinding | None = None,
    comments_text: str = "",
) -> tuple[CandidateIssue, str]:
    if not getattr(candidate, "resumed", False):
        candidate = await _maybe_compact_context(
            config,
            adapter,
            candidate,
            agent_runner,
            now=now,
            binding=binding,
        )
    prompt = _invoke_renderer(
        render_prompt,
        candidate,
        resume=getattr(candidate, "resumed", False),
    )
    if comments_text and not getattr(candidate, "resumed", False):
        prompt = f"{prompt}\n\n{render_previous_comments_block(comments_text)}"
    return candidate, prompt


async def _maybe_compact_context(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    agent_runner: Callable[..., AgentResult],
    *,
    now: Callable[[], datetime],
    binding: ProjectBinding | None = None,
) -> CandidateIssue:
    if not getattr(adapter, "stores_context", False):
        return candidate
    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    if resolved_binding is None:
        return candidate
    if resolved_binding.is_remote:
        # Remote compaction is a documented follow-up (ADR-0012): the compaction
        # agent's cwd would be the remote repo_path, so skip it for now and
        # dispatch the candidate uncompacted. Routing the compaction agent
        # through the remote adapter is deferred.
        return candidate
    replace_context = getattr(adapter, "replace_context", None)
    if not callable(replace_context):
        return candidate
    settings_fn = getattr(adapter, "context_compaction_settings", None)
    settings = {
        "threshold_tokens": 16_000,
        "keep_recent_runs": 3,
    }
    if callable(settings_fn):
        settings.update(
            await _maybe_await(
                settings_fn(
                    getattr(candidate, "binding_name", "") or resolved_binding.name
                )
            )
        )
    context = str(getattr(candidate, "context_md", "") or "")
    if estimate_tokens(context) <= int(settings["threshold_tokens"]):
        return candidate
    try:
        pi_entry = resolve_model(None, load_models(), agent="pi")
    except Exception as exc:
        raise SchedulerContextCompactionError(
            f"context compaction model resolution failed: {exc}"
        ) from exc
    compaction_candidate = replace(
        candidate,
        resolved_provider=str(pi_entry["provider"]),
        resolved_model=f"{pi_entry['id']}:high",
    )
    try:
        compacted = await asyncio.to_thread(
            maybe_compact,
            compaction_candidate,
            resolved_binding,
            agent_runner,
            threshold_tokens=int(settings["threshold_tokens"]),
            keep_recent_runs=int(settings["keep_recent_runs"]),
            now=now,
        )
    except Exception as exc:
        if isinstance(exc, ContextCompactionError):
            raise SchedulerContextCompactionError(str(exc)) from exc
        raise
    if compacted == str(getattr(candidate, "context_md", "") or ""):
        return candidate
    updated_issue = await _maybe_await(replace_context(candidate.id, compacted))
    return replace(
        candidate,
        context_md=str(updated_issue.get("context_md") or compacted),
    )


def _apply_dispatch_gate(
    candidate: CandidateIssue, binding: ProjectBinding | None
) -> tuple[CandidateIssue, str | None]:
    """Resolve agent, model, and skill for a Podium dispatch.

    Returns the candidate annotated with the resolved pi provider/model, or an
    error message describing why dispatch must block. Fail-loud contract: an
    unwired agent, an unknown model, or a missing skill never falls back to
    defaults silently.
    """
    agent = binding.resolve_agent(candidate.labels) if binding is not None else "pi"
    if binding is not None and binding.is_remote:
        if agent != "pi":
            return candidate, (
                "Dispatch blocked: remote bindings support only pi in v1 "
                "(ADR-0012); clear the agent:claude label / preferred_agent."
            )
        if getattr(candidate, "preferred_skill", None):
            return candidate, (
                "Dispatch blocked: remote bindings do not support "
                "preferred_skill in v1 (ADR-0012); clear preferred_skill or run "
                "on a local binding."
            )
    try:
        entry = resolve_model(
            getattr(candidate, "preferred_model", None), load_models(), agent=agent
        )
    except Exception as exc:
        return candidate, f"Dispatch blocked: model resolution failed: {exc}"
    if entry["agent"] != agent:
        return candidate, (
            f"Dispatch blocked: model `{entry['id']}` requires agent "
            f"`{entry['agent']}` but the issue resolves to agent `{agent}`; "
            "pick a matching model or change preferred_agent."
        )
    if agent == "claude" and (probe_failure := claude_probe_failure_reason()):
        return candidate, (
            "Dispatch blocked: claude engine probe failed at startup: "
            f"{probe_failure}. Fix the install and restart."
        )
    skill = getattr(candidate, "preferred_skill", None)
    if skill:
        skill_source = getattr(candidate, "skill_source", "")
        if not skill_source:
            return candidate, (
                f"Dispatch blocked: skill `{skill}` is not in the Podium "
                "skill catalog. Refresh the catalog or clear preferred_skill."
            )
        if not Path(skill_source).is_file():
            return candidate, (
                f"Dispatch blocked: skill source for `{skill}` is missing "
                f"on disk: {skill_source}"
            )
    if agent == "pi":
        effort = getattr(candidate, "reasoning_effort", "") or "high"
        # Reasoning-effort vocabulary is model-specific (e.g. gpt-5.5 dropped
        # 'minimal' for 'none' and added 'xhigh'). Reject an unsupported effort
        # here so dispatch fails loudly instead of the provider failing the run
        # ~8s in. Entries without `efforts` are not validated (back-compat).
        supported = entry.get("efforts")
        if supported and effort not in supported:
            return candidate, (
                f"Dispatch blocked: reasoning_effort `{effort}` is not supported "
                f"by model `{entry['id']}`; supported: {', '.join(supported)}. "
                "Pick a supported effort or clear reasoning_effort."
            )
        return (
            replace(
                candidate,
                resolved_provider=str(entry["provider"]),
                resolved_model=f"{entry['id']}:{effort}",
            ),
            None,
        )
    return (
        replace(
            candidate,
            resolved_provider="",
            resolved_model=str(entry["id"]),
        ),
        None,
    )


async def _start_run_record(
    adapter: TrackerAdapter,
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None = None,
) -> tuple[str | None, Path | None]:
    if not getattr(adapter, "stores_context", False):
        return None, None
    record_run = getattr(adapter, "record_run", None)
    update_run = getattr(adapter, "update_run", None)
    if not callable(record_run) or not callable(update_run):
        return None, None
    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    agent = (
        resolved_binding.resolve_agent(candidate.labels)
        if resolved_binding is not None
        else "pi"
    )
    base_branch = getattr(candidate, "base_branch", "") or config.base_branch
    resolved_provider = getattr(candidate, "resolved_provider", "")
    resolved_model = getattr(candidate, "resolved_model", "")
    if agent == "pi":
        resolved_provider = resolved_provider or config.pi_provider
        resolved_model = resolved_model or config.pi_model
    run_payload = {
        "issue_id": candidate.id,
        "agent": agent,
        # Resolved by the dispatch gate from models.yml; legacy config fallback
        # applies only to pi. Non-pi agents store resolved fields verbatim.
        "provider": resolved_provider,
        "model": resolved_model,
        "state": "queued",
        "base_branch": base_branch,
        "skill_invoked": getattr(candidate, "preferred_skill", None),
        "agent_session_sha": getattr(candidate, "agent_session_sha", "") or None,
        "resumed": bool(getattr(candidate, "resumed", False)),
        **_worktree_run_fields(
            config, candidate, base_branch, binding=resolved_binding
        ),
    }
    run = await _maybe_await(
        cast(Callable[[dict[str, Any]], Any], record_run)(run_payload)
    )
    run_id = str(run.get("id") or "")
    if not run_id:
        return None, None
    adapter_db_path = getattr(adapter, "db_path", None)
    run_log_root = (
        Path(adapter_db_path).parent / "runs"
        if adapter_db_path is not None
        else resolve_run_log_root()
    )
    return run_id, (run_log_root / f"{run_id}.log").resolve()


async def _mark_run_record_running(
    adapter: TrackerAdapter,
    run_id: str | None,
    log_path: Path | None,
    *,
    started_at: str,
) -> None:
    if not run_id or log_path is None:
        return
    update_run = getattr(adapter, "update_run", None)
    if not callable(update_run):
        return
    await _maybe_await(
        cast(Callable[[str, dict[str, Any]], Any], update_run)(
            run_id,
            {"state": "running", "started_at": started_at, "log_path": str(log_path)},
        )
    )


async def _finish_run_record(
    adapter: TrackerAdapter,
    run_id: str | None,
    log_path: Path | None,
    *,
    result: AgentResult,
    secrets: Sequence[str],
    state: str,
    verdict: str | None,
    summary: str | None,
    ended_at: str,
) -> None:
    if not run_id or log_path is None:
        return
    # The run log carries far more than the 2 KB comment/context report so the
    # run-detail pane shows full output; secrets are still redacted and ANSI
    # stripped, only the truncation bound differs.
    _write_run_log(
        log_path,
        _sanitize_report(result.stdout, secrets, max_bytes=LOG_MAX_BYTES),
        _sanitize_report(result.stderr, secrets, max_bytes=LOG_MAX_BYTES),
    )
    update_run = getattr(adapter, "update_run", None)
    if not callable(update_run):
        return
    await _maybe_await(
        cast(Callable[[str, dict[str, Any]], Any], update_run)(
            run_id,
            {
                "state": state,
                "verdict": verdict,
                "summary": summary,
                "exit_code": result.exit_code,
                "ended_at": ended_at,
                "log_path": str(log_path),
                **_parse_run_metrics(result.stdout),
            },
        )
    )


async def _handle_archived_terminal(
    adapter: TrackerAdapter,
    config: SymphonyConfig,
    candidate: CandidateIssue,
    run_id: str | None,
    *,
    binding: ProjectBinding | None = None,
) -> bool:
    """Return True when a completed Run's issue was archived mid-run.

    Archived is terminal for engine verdict transitions: run rows still finish,
    but issue.state is not resurrected and persistent worktrees are discarded.
    """
    issue = await _fetch_issue(adapter, candidate.id)
    if str(issue.get("state") or "") != "archived":
        return False

    LOGGER.info(
        "archived_terminal issue_id=%s run_id=%s",
        candidate.id,
        run_id or "",
    )

    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    binding_name = str(
        getattr(candidate, "binding_name", "")
        or (resolved_binding.name if resolved_binding is not None else "")
    )
    if not binding_name:
        return True

    # Remote bindings have no local worktree (ADR-0012); the worktree_exists /
    # remove_worktree helpers run local git/Path ops against
    # config.homelab_repo_path, which is the remote path for a remote binding
    # (→ PermissionError). Skip them but still clear the worktree_active column.
    is_remote = resolved_binding is not None and resolved_binding.is_remote
    if not is_remote:
        worktree_helpers = import_module("worktree_facade")
        remove_worktree = worktree_helpers.remove_worktree
        worktree_exists = worktree_helpers.worktree_exists

        issue_id = str(candidate.id)
        if await asyncio.to_thread(
            worktree_exists, config.homelab_repo_path, binding_name, issue_id
        ):
            await asyncio.to_thread(
                remove_worktree, config.homelab_repo_path, binding_name, issue_id
            )

    update_columns = getattr(adapter, "_update_issue_columns", None)
    if callable(update_columns) and issue.get("worktree_active"):
        await _maybe_await(update_columns(candidate.id, {"worktree_active": False}))
    return True


class LockHeld(RuntimeError):
    """Raised when another scheduler owns the workspace lock."""


@dataclass(frozen=True)
class TickResult:
    dispatched: bool
    reason: str
    issue_id: str | None = None
    mode: str = "execute"


@dataclass(frozen=True)
class _ResumeFallbackResult:
    candidate: CandidateIssue
    result: AgentResult
    run_id: str | None
    run_log_path: Path | None
    claim_dt: datetime


@dataclass(frozen=True)
class _ScheduledSelection:
    candidate: CandidateIssue
    reason: str
    event: ScheduleEvent | None = None
    error: str = ""


def _labels_contain_role(
    labels: tuple[str, ...] | list[str],
    tracker: TrackerAdapter | TrackerContract,
    role: TrackerRole,
) -> bool:
    if hasattr(tracker, "labels_contain_role"):
        return cast(TrackerAdapter, tracker).labels_contain_role(labels, role)
    contract = cast(TrackerContract, tracker)
    binding = contract.optional_label_binding(role)
    if binding is None:
        return False
    values = {binding.name}
    if binding.uuid:
        values.add(binding.uuid)
    return bool(values & set(labels))


def _resolve_mode(
    labels: tuple[str, ...],
    tracker: TrackerAdapter | TrackerContract = DEFAULT_CONTRACT,
) -> str:
    if _labels_contain_role(labels, tracker, TrackerRole.MODE_BUILD):
        return "build"
    if _labels_contain_role(labels, tracker, TrackerRole.MODE_PLAN):
        return "plan"
    return "conversation"


def _binding_approval_enabled(binding: ProjectBinding | None) -> bool:
    return bool(binding and binding.approval_policy.enabled)


def _issue_slug(issue: CandidateIssue) -> str:
    raw = issue.identifier or issue.id
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug or issue.id


def _expected_plan_path(repo_path: Path, issue: CandidateIssue) -> Path:
    return (repo_path / "plans" / f"{_issue_slug(issue)}.md").resolve()


def _state_path_for_plan(plan_path: Path) -> Path:
    return plan_path.with_name(f".{plan_path.stem}.state.yml")


def _final_non_empty_line(body: str) -> str | None:
    for line in reversed(body.splitlines()):
        stripped = line.strip().strip("`")
        if stripped:
            return stripped
    return None


def _validate_issue_plan_path(
    repo_path: Path, issue: CandidateIssue, raw_path: str
) -> Path:
    expected = _expected_plan_path(repo_path, issue)
    plans_dir = (repo_path / "plans").resolve()
    candidate = Path(raw_path).expanduser().resolve()
    if not raw_path.startswith("/"):
        raise ValueError("plan path is not absolute")
    if candidate != expected:
        raise ValueError("plan path does not match the current issue slug")
    if candidate.parent != plans_dir:
        raise ValueError("plan path is outside the homelab plans directory")
    if candidate.suffix != ".md":
        raise ValueError("plan path is not a Markdown file")
    if not candidate.is_file():
        raise ValueError("plan path is not a readable regular file")
    return candidate


def _validated_fallback_plan_path(
    repo_path: Path, issue: CandidateIssue
) -> Path | None:
    expected = _expected_plan_path(repo_path, issue)
    try:
        return _validate_issue_plan_path(repo_path, issue, str(expected))
    except ValueError:
        return None


async def _dispatch_with_resume_fallback(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    render_prompt: Callable[..., str],
    agent_runner: Callable[..., AgentResult],
    *,
    now: Callable[[], datetime],
    binding: ProjectBinding | None,
    comments_text: str,
    compaction_agent_runner: Callable[..., AgentResult] | None,
    run_id: str | None,
    run_log_path: Path | None,
    failed_result: AgentResult,
    secrets: Sequence[str],
    resume_summary: str,
    mode: str,
    notifier: TelegramNotifier | None,
    resume_error: Exception | None = None,
) -> _ResumeFallbackResult | TickResult:
    """Record a failed resumed dispatch, then retry once as a fresh dispatch."""

    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=failed_result,
        secrets=secrets,
        state="failed",
        verdict="blocked",
        summary=resume_summary,
        ended_at=now().isoformat(),
    )
    if resume_error is not None:
        LOGGER.warning(
            "resume_failed issue_id=%s error=%s fell_back=true",
            candidate.id,
            resume_error,
        )
    else:
        LOGGER.warning(
            "resume_failed issue_id=%s exit_code=%s fell_back=true",
            candidate.id,
            failed_result.exit_code,
        )

    fallback_cwd = _dispatch_cwd(config, candidate, binding=binding)
    candidate = replace(
        candidate,
        resumed=False,
        agent_session_sha=(
            repo_host_for(binding, cwd=fallback_cwd).code_sha()
            if binding is not None
            else resolve_code_sha(fallback_cwd)
        ),
    )
    fallback_run_id = run_id
    fallback_run_log_path = run_log_path
    try:
        candidate, prompt = await _render_for_dispatch(
            config,
            adapter,
            candidate,
            render_prompt,
            compaction_agent_runner or agent_runner,
            now=now,
            binding=binding,
            comments_text=comments_text,
        )
        fallback_run_id, fallback_run_log_path = await _start_run_record(
            adapter, config, candidate, binding=binding
        )
        candidate = replace(candidate, active_run_id=fallback_run_id or "")
        claim_time = now().isoformat()
        await _mark_run_record_running(
            adapter,
            fallback_run_id,
            fallback_run_log_path,
            started_at=claim_time,
        )
        claim_dt = datetime.fromisoformat(claim_time)
        result = await asyncio.to_thread(agent_runner, candidate, prompt)
    except Exception as exc:
        result = AgentResult(1, 0, False, stdout="", stderr=str(exc))
        await _finish_run_record(
            adapter,
            fallback_run_id,
            fallback_run_log_path,
            result=result,
            secrets=secrets,
            state="failed",
            verdict="blocked",
            summary=f"Agent crashed: {exc}",
            ended_at=now().isoformat(),
        )
        _iu, _du = _build_urls(config, candidate.id)
        await _block_issue(
            adapter,
            candidate.id,
            f"Agent crashed: {exc}",
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return TickResult(True, "agent-crashed", candidate.id, mode=mode)

    return _ResumeFallbackResult(
        candidate=candidate,
        result=result,
        run_id=fallback_run_id,
        run_log_path=fallback_run_log_path,
        claim_dt=claim_dt,
    )


async def run_tick(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    agent_runner: Callable[..., AgentResult],
    render_prompt: Callable[[CandidateIssue], str],
    compaction_agent_runner: Callable[..., AgentResult] | None = None,
    lock_path: Path | None = None,
    poller: Callable[[TrackerAdapter], Any] | None = None,
    repo_dirty: Callable[[Path], bool] | None = None,
    diff_stat: Callable[[Path], str] | None = None,
    auto_commit: Callable[..., str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    run_blocked_reconciler: bool = True,
    dispatch_state: _DispatchState | None = None,
    binding: ProjectBinding | None = None,
) -> TickResult:
    """Run one scheduler tick without sleeping forever."""

    tick_binding = binding or _binding_from_config(config)
    is_coding = tick_binding is not None and tick_binding.binding_type == "coding"

    dispatch_state = dispatch_state or _new_dispatch_state(config)
    await reconcile_pending_review(config, adapter, dispatch_state, notifier=notifier)

    try:
        await reconcile_stale_running(
            adapter,
            config.run_timeout_ms,
            now=now,
            notifier=notifier,
            dispatch_state=dispatch_state,
        )
        if (
            config.blocked_reconciler_enabled
            and not is_coding
            and run_blocked_reconciler
        ):
            try:
                await reconcile_blocked(
                    adapter,
                    apply=config.blocked_reconciler_apply,
                    now=now,
                )
            except PlaneRateLimitError:
                raise
            except Exception as exc:
                LOGGER.warning("blocked_reconcile_failed error=%s", exc, exc_info=True)
        scheduled_reserved = False
        scheduled = (
            None if is_coding else await _select_scheduled_candidate(adapter, now=now)
        )
    except PlaneRateLimitError:
        raise
    if scheduled is not None:
        if scheduled.reason == "scheduled-release":
            candidate = scheduled.candidate
            if not await _reserve_specific_candidate(
                candidate, dispatch_state=dispatch_state
            ):
                return TickResult(False, "already-in-flight", candidate.id)
            scheduled_reserved = True
            try:
                released_event = await _release_scheduled_candidate(
                    adapter, candidate.id, scheduled.event
                )
            except PlaneRateLimitError:
                raise
            except Exception as exc:
                try:
                    _iu, _du = _build_urls(config, candidate.id)
                    await _block_issue(
                        adapter,
                        candidate.id,
                        f"Scheduled release failed after becoming due: {exc}",
                        issue_name=candidate.name,
                        issue_identifier=candidate.identifier,
                        notifier=notifier,
                        issue_url=_iu,
                        dashboard_url=_du,
                    )
                finally:
                    await _release_candidate(
                        candidate.id, dispatch_state=dispatch_state
                    )
                    scheduled_reserved = False
                return TickResult(False, "scheduled-release-failed", candidate.id)
            candidate = _with_schedule_context(
                scheduled.candidate, released_event, now=now()
            )
        elif scheduled.reason == "scheduled-missing":
            _iu, _du = _build_urls(config, scheduled.candidate.id)
            await _block_issue(
                adapter,
                scheduled.candidate.id,
                "Scheduled ticket is missing a valid Symphony-Schedule comment.",
                issue_name=scheduled.candidate.name,
                issue_identifier=scheduled.candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return TickResult(False, "scheduled-missing", scheduled.candidate.id)
        elif scheduled.reason == "scheduled-malformed":
            _iu, _du = _build_urls(config, scheduled.candidate.id)
            await _block_issue(
                adapter,
                scheduled.candidate.id,
                f"Scheduled ticket has a malformed latest schedule comment: {scheduled.error}",
                issue_name=scheduled.candidate.name,
                issue_identifier=scheduled.candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return TickResult(False, "scheduled-malformed", scheduled.candidate.id)
        elif scheduled.reason == "scheduled-cancelled":
            await _repair_cancelled_schedule(
                adapter, scheduled.candidate.id, scheduled.event
            )
            return TickResult(False, "scheduled-cancelled", scheduled.candidate.id)
        else:
            candidate = None
    else:
        candidate = None

    try:
        candidates = (
            []
            if candidate is not None
            else await _maybe_await(
                poller(adapter) if poller is not None else adapter.list_candidates()
            )
        )
    except PlaneRateLimitError:
        raise
    except Exception as exc:
        LOGGER.warning("plane_poll_failed error=%s", exc)
        return TickResult(False, "plane-unreachable")
    _clear_rate_limit(dispatch_state)

    approval_policy_enabled = _binding_approval_enabled(tick_binding) and not is_coding
    if candidate is None:
        candidate = await _reserve_candidate(
            candidates,
            adapter.contract,
            approval_policy_enabled=approval_policy_enabled,
            dispatch_state=dispatch_state,
        )
    elif not scheduled_reserved and not await _reserve_specific_candidate(
        candidate,
        dispatch_state=dispatch_state,
    ):
        return TickResult(False, "already-in-flight", candidate.id)
    if candidate is None:
        return TickResult(False, "no-candidates")

    try:
        if approval_policy_enabled and adapter.labels_contain_role(
            candidate.labels, TrackerRole.APPROVAL_REQUIRED
        ):
            return TickResult(False, "approval-required", candidate.id)

        mode = _resolve_mode(candidate.labels, adapter.contract)

        fresh = await _fetch_issue(adapter, candidate.id)
        if not _is_state(
            fresh,
            adapter.contract.state_name_for_role(TrackerRole.STATE_TODO),
            adapter.contract.state_value_for_role(TrackerRole.STATE_TODO),
        ):
            return TickResult(False, "state-changed", candidate.id)
        label_ids = adapter.contract.label_ids if adapter.contract else None
        fresh_labels = _extract_labels(fresh, label_ids=label_ids)
        if approval_policy_enabled and adapter.labels_contain_role(
            fresh_labels, TrackerRole.APPROVAL_REQUIRED
        ):
            return TickResult(False, "approval-required", candidate.id)

        if adapter.labels_contain_role(fresh_labels, TrackerRole.SCHEDULED):
            return TickResult(False, "scheduled-held", candidate.id)

        if mode == "build" and not is_coding:
            if adapter.labels_contain_role(fresh_labels, TrackerRole.MODE_PLAN):
                try:
                    await adapter.remove_labels(candidate.id, [TrackerRole.MODE_PLAN])
                except PlaneRateLimitError:
                    raise
                except Exception as exc:
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(
                            body=f"Build could not start: failed to remove stale `plan` label: {exc}"
                        ),
                    )
                    return TickResult(
                        False, "stale-plan-label-remove-failed", candidate.id, mode=mode
                    )

            plan_path = _validated_fallback_plan_path(
                config.homelab_repo_path, candidate
            )
            if plan_path is None:
                try:
                    await adapter.add_labels(candidate.id, [TrackerRole.MODE_PLAN])
                    await adapter.remove_labels(candidate.id, [TrackerRole.MODE_BUILD])
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(
                            body=(
                                "Build could not start because no readable plan file was found. "
                                "Returning this issue to Plan mode so Symphony can regenerate and post the plan."
                            )
                        ),
                    )
                    await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
                except PlaneRateLimitError:
                    raise
                except Exception as exc:
                    _iu, _du = _build_urls(config, candidate.id)
                    await _block_issue(
                        adapter,
                        candidate.id,
                        f"Build plan recovery failed after no readable plan was found: {exc}",
                        issue_name=candidate.name,
                        issue_identifier=candidate.identifier,
                        notifier=notifier,
                        issue_url=_iu,
                        dashboard_url=_du,
                    )
                    return TickResult(
                        False, "build-plan-recovery-failed", candidate.id, mode=mode
                    )
                return TickResult(
                    False,
                    "build-plan-missing-returned-to-plan",
                    candidate.id,
                    mode=mode,
                )

        # Dispatch gate (Podium only): resolve agent, model, and skill before
        # any state transition or compaction spend. Anything unresolvable
        # blocks loudly instead of silently dispatching different settings.
        if getattr(adapter, "stores_context", False):
            candidate, gate_error = _apply_dispatch_gate(candidate, tick_binding)
            if gate_error is not None:
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    gate_error,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(
                    False, "dispatch-gate-blocked", candidate.id, mode=mode
                )

        try:
            comments_text = await _fetch_issue_comments(adapter, candidate.id)
            candidate, _resume_decision = await _prepare_resume_candidate(
                adapter,
                config,
                candidate,
                fresh,
                binding=tick_binding,
            )
            candidate, prompt = await _render_for_dispatch(
                config,
                adapter,
                candidate,
                render_prompt,
                compaction_agent_runner or agent_runner,
                now=now,
                binding=tick_binding,
                comments_text=comments_text,
            )
        except SchedulerContextCompactionError as exc:
            _iu, _du = _build_urls(config, candidate.id)
            await _block_issue(
                adapter,
                candidate.id,
                f"Context compaction failed: {exc}",
                issue_name=candidate.name,
                issue_identifier=candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return TickResult(
                False, "context-compaction-failed", candidate.id, mode=mode
            )
        except OSError as exc:
            _iu, _du = _build_urls(config, candidate.id)
            await _block_issue(
                adapter,
                candidate.id,
                f"Workflow prompt could not be rendered: {exc}",
                issue_name=candidate.name,
                issue_identifier=candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return TickResult(False, "workflow-missing", candidate.id, mode=mode)

        try:
            run_id, run_log_path = await _start_run_record(
                adapter, config, candidate, binding=tick_binding
            )
            candidate = replace(candidate, active_run_id=run_id or "")
            # preferred_skill is consume-on-dispatch (ADR-0008): captured into
            # run.skill_invoked above, cleared once the Run row is recorded.
            # Compare-and-clear so a concurrent operator re-pick survives; only
            # runs for stores_context adapters (run_id is not None — Plane
            # returns None and is untouched). Mirrors the guarded-getattr at
            # the worktree-column clear above. Does not touch preferred_model
            # or reasoning_effort (those stay standing config).
            consumed_skill = getattr(candidate, "preferred_skill", None)
            if run_id is not None and consumed_skill:
                consume = getattr(adapter, "consume_preferred_skill", None)
                if callable(consume):
                    await _maybe_await(consume(candidate.id, consumed_skill))
            await adapter.transition_state(candidate.id, TrackerRole.STATE_RUNNING)
            claim_time = now().isoformat()
            await _mark_run_record_running(
                adapter,
                run_id,
                run_log_path,
                started_at=claim_time,
            )
            # Claim time is persisted by the Run record (started_at) above; no
            # claim comment is posted so the human comment stream stays clean.
            claim_dt = datetime.fromisoformat(claim_time)
            LOGGER.info(
                "issue_claimed issue_id=%s claimed_at=%s", candidate.id, claim_time
            )

            secrets = _collect_secrets(config)
            dispatch_agent = (
                tick_binding.resolve_agent(candidate.labels)
                if tick_binding is not None
                else "pi"
            )
            parse_stderr = dispatch_agent != "claude"

            result: AgentResult | None = None
            try:
                result = await asyncio.to_thread(agent_runner, candidate, prompt)
            except Exception as exc:
                if getattr(candidate, "resumed", False):
                    fallback = await _dispatch_with_resume_fallback(
                        config,
                        adapter,
                        candidate,
                        render_prompt,
                        agent_runner,
                        now=now,
                        binding=tick_binding,
                        comments_text=comments_text,
                        compaction_agent_runner=compaction_agent_runner,
                        run_id=run_id,
                        run_log_path=run_log_path,
                        failed_result=AgentResult(
                            1, 0, False, stdout="", stderr=str(exc)
                        ),
                        secrets=secrets,
                        resume_summary=f"resume_failed: {exc}; fell_back=true",
                        mode=mode,
                        notifier=notifier,
                        resume_error=exc,
                    )
                    if isinstance(fallback, TickResult):
                        return fallback
                    candidate = fallback.candidate
                    result = fallback.result
                    run_id = fallback.run_id
                    run_log_path = fallback.run_log_path
                    claim_dt = fallback.claim_dt
                else:
                    result = AgentResult(1, 0, False, stdout="", stderr=str(exc))
                    await _finish_run_record(
                        adapter,
                        run_id,
                        run_log_path,
                        result=result,
                        secrets=secrets,
                        state="failed",
                        verdict="blocked",
                        summary=f"Agent crashed: {exc}",
                        ended_at=now().isoformat(),
                    )
                    _iu, _du = _build_urls(config, candidate.id)
                    await _block_issue(
                        adapter,
                        candidate.id,
                        f"Agent crashed: {exc}",
                        issue_name=candidate.name,
                        issue_identifier=candidate.identifier,
                        notifier=notifier,
                        issue_url=_iu,
                        dashboard_url=_du,
                    )
                    return TickResult(True, "agent-crashed", candidate.id, mode=mode)
            assert result is not None

            LOGGER.info(
                "agent_exited issue_id=%s exit_code=%s duration_ms=%s timed_out=%s",
                candidate.id,
                result.exit_code,
                result.duration_ms,
                str(result.timed_out).lower(),
            )
            if (
                getattr(candidate, "resumed", False)
                and result.exit_code != 0
                and not result.timed_out
            ):
                fallback = await _dispatch_with_resume_fallback(
                    config,
                    adapter,
                    candidate,
                    render_prompt,
                    agent_runner,
                    now=now,
                    binding=tick_binding,
                    comments_text=comments_text,
                    compaction_agent_runner=compaction_agent_runner,
                    run_id=run_id,
                    run_log_path=run_log_path,
                    failed_result=result,
                    secrets=secrets,
                    resume_summary=(
                        f"resume_failed: exit code {result.exit_code}; fell_back=true"
                    ),
                    mode=mode,
                    notifier=notifier,
                )
                if isinstance(fallback, TickResult):
                    return fallback
                candidate = fallback.candidate
                result = fallback.result
                run_id = fallback.run_id
                run_log_path = fallback.run_log_path
                claim_dt = fallback.claim_dt
            if result.timed_out:
                msg = f"Agent timed out after {result.duration_ms} ms"
                stdout, stderr = _format_report(result, secrets)
                summary = _extract_summary(result, secrets, include_stderr=parse_stderr)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    secrets=secrets,
                    state="failed",
                    verdict="blocked",
                    summary=summary or "Agent timed out.",
                    ended_at=now().isoformat(),
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    msg,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "timeout", candidate.id, mode=mode)
            if result.exit_code != 0:
                msg = f"Agent failed with exit code {result.exit_code} after {result.duration_ms} ms"
                stdout, stderr = _format_report(result, secrets)
                summary = _extract_summary(result, secrets, include_stderr=parse_stderr)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    secrets=secrets,
                    state="failed",
                    verdict="blocked",
                    summary=summary
                    or f"Agent failed with exit code {result.exit_code}.",
                    ended_at=now().isoformat(),
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    msg,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "nonzero", candidate.id, mode=mode)

            stdout, stderr = _format_report(result, secrets)
            gate_stderr = stderr if parse_stderr else ""

            if not is_coding:
                scheduled_after_agent = await _detect_agent_schedule(
                    adapter,
                    candidate,
                    claim_dt=claim_dt,
                    stdout=stdout,
                    stderr=stderr,
                    notifier=notifier,
                    config=config,
                )
                if scheduled_after_agent is not None:
                    return TickResult(
                        True, scheduled_after_agent, candidate.id, mode=mode
                    )

            if _hit_permission_gate(stdout, gate_stderr):
                msg = (
                    "Agent could not complete because required tool access was denied."
                )
                summary = _extract_summary(result, secrets, include_stderr=parse_stderr)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    secrets=secrets,
                    state="failed",
                    verdict="blocked",
                    summary=summary or msg,
                    ended_at=now().isoformat(),
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    msg,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "permission-gate", candidate.id, mode=mode)

            if _hit_approval_gate(stdout, gate_stderr):
                msg = "Agent could not complete because operator approval is required."
                summary = _extract_summary(result, secrets, include_stderr=parse_stderr)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    secrets=secrets,
                    state="failed",
                    verdict="blocked",
                    summary=summary or msg,
                    ended_at=now().isoformat(),
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    msg,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "approval-gate", candidate.id, mode=mode)

            verdict = _parse_result_marker(stdout)
            summary = _extract_summary(result, secrets, include_stderr=parse_stderr)
            question = _extract_question(result, secrets, include_stderr=parse_stderr)

            def _completion_body() -> str:
                if summary:
                    # Block on its own line so a leading markdown heading in the
                    # agent's summary renders correctly.
                    return f"**Symphony completed:**\n\n{summary}"
                return "**Symphony completed:** Agent finished without a summary."

            if verdict == "blocked":
                if summary:
                    msg = summary
                else:
                    msg = "Agent reported a blocked result."
                    if stderr:
                        msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    secrets=secrets,
                    state="failed",
                    verdict="blocked",
                    summary=summary or "Agent reported a blocked result.",
                    ended_at=now().isoformat(),
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    msg,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "agent-marker-blocked", candidate.id, mode=mode)

            if question:
                question_body = f"**Symphony question:**\n\n{question}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    secrets=secrets,
                    state="succeeded",
                    # Persist an allowed verdict while the question text and
                    # agent-question-park reason carry the Question Park outcome.
                    # Podium's schema constrains verdicts to done/review/blocked.
                    verdict="review",
                    summary=question,
                    ended_at=now().isoformat(),
                )
                try:
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(body=question_body),
                    )
                    if getattr(adapter, "stores_context", False):
                        context_parts = []
                        if stdout:
                            context_parts.append(
                                f"## Agent stdout\n\n```\n{stdout}\n```"
                            )
                        if stderr:
                            context_parts.append(
                                f"## Agent stderr\n\n```\n{stderr}\n```"
                            )
                        if context_parts:
                            await adapter.append_context(
                                candidate.id, "\n\n".join(context_parts)
                            )
                except PlaneRateLimitError:
                    if dispatch_state is not None:
                        dispatch_state.pending_review_issue_ids.add(candidate.id)
                        dispatch_state.pending_completion_bodies[candidate.id] = (
                            question_body
                        )
                        LOGGER.info(
                            "pending_review_queued issue_id=%s reason=agent-question-park (post-agent comment/context rate-limited)",
                            candidate.id,
                        )
                    raise
                if await _handle_archived_terminal(
                    adapter, config, candidate, run_id, binding=tick_binding
                ):
                    return TickResult(
                        True, "archived-terminal", candidate.id, mode=mode
                    )
                try:
                    await adapter.transition_state(
                        candidate.id, TrackerRole.STATE_IN_REVIEW
                    )
                except PlaneRateLimitError:
                    if dispatch_state is not None:
                        dispatch_state.pending_review_issue_ids.add(candidate.id)
                        LOGGER.info(
                            "pending_review_queued issue_id=%s reason=agent-question-park (post-agent transition rate-limited)",
                            candidate.id,
                        )
                    raise
                LOGGER.info(
                    "state_transitioned issue_id=%s state=in-review reason=agent-question-park",
                    candidate.id,
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _notify_review(
                    notifier,
                    candidate.name,
                    candidate.identifier,
                    reason="Operator question parked",
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "agent-question-park", candidate.id, mode=mode)

            if not is_coding:
                after_agent = await _fetch_issue(adapter, candidate.id)
                if _is_state(
                    after_agent,
                    adapter.contract.state_name_for_role(TrackerRole.STATE_IN_REVIEW),
                    adapter.contract.state_value_for_role(TrackerRole.STATE_IN_REVIEW),
                ):
                    return TickResult(True, "agent-review", candidate.id, mode=mode)
                if _is_state(
                    after_agent,
                    adapter.contract.state_name_for_role(TrackerRole.STATE_BLOCKED),
                    adapter.contract.state_value_for_role(TrackerRole.STATE_BLOCKED),
                ):
                    return TickResult(True, "agent-blocked", candidate.id, mode=mode)

            reason_code = (
                "agent-marker-review"
                if verdict in {"review", "done"}
                else "agent-clean-review"
            )
            completion_body = _completion_body()
            await _finish_run_record(
                adapter,
                run_id,
                run_log_path,
                result=result,
                secrets=secrets,
                state="succeeded",
                verdict=verdict or "review",
                summary=summary,
                ended_at=now().isoformat(),
            )
            try:
                await adapter.add_comment(
                    candidate.id,
                    CommentPayload(body=completion_body),
                )
                if getattr(adapter, "stores_context", False):
                    context_parts = []
                    if stdout:
                        context_parts.append(f"## Agent stdout\n\n```\n{stdout}\n```")
                    if stderr:
                        context_parts.append(f"## Agent stderr\n\n```\n{stderr}\n```")
                    if context_parts:
                        await adapter.append_context(
                            candidate.id, "\n\n".join(context_parts)
                        )
            except PlaneRateLimitError:
                if dispatch_state is not None:
                    dispatch_state.pending_review_issue_ids.add(candidate.id)
                    dispatch_state.pending_completion_bodies[candidate.id] = (
                        completion_body
                    )
                    LOGGER.info(
                        "pending_review_queued issue_id=%s reason=%s (post-agent comment/context rate-limited)",
                        candidate.id,
                        reason_code,
                    )
                raise
            if await _handle_archived_terminal(
                adapter, config, candidate, run_id, binding=tick_binding
            ):
                return TickResult(True, "archived-terminal", candidate.id, mode=mode)
            try:
                await adapter.transition_state(
                    candidate.id, TrackerRole.STATE_IN_REVIEW
                )
            except PlaneRateLimitError:
                if dispatch_state is not None:
                    dispatch_state.pending_review_issue_ids.add(candidate.id)
                    LOGGER.info(
                        "pending_review_queued issue_id=%s reason=%s (post-agent transition rate-limited)",
                        candidate.id,
                        reason_code,
                    )
                raise
            LOGGER.info(
                "state_transitioned issue_id=%s state=in-review reason=%s",
                candidate.id,
                reason_code,
            )
            _iu, _du = _build_urls(config, candidate.id)
            await _notify_review(
                notifier,
                candidate.name,
                candidate.identifier,
                reason=(
                    "Conversation response ready"
                    if mode == "conversation"
                    else "Agent completed, awaiting review"
                ),
                issue_url=_iu,
                dashboard_url=_du,
            )
            return TickResult(True, reason_code, candidate.id, mode=mode)

        except Exception:
            raise
    except Exception:
        raise
    finally:
        await _release_candidate(candidate.id, dispatch_state=dispatch_state)


async def _dispatch_one(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    agent_runner: AgentAdapter,
    render_prompt: Callable[[CandidateIssue], str],
    notifier: TelegramNotifier | None,
    run_blocked_reconciler: bool,
    dispatch_state: _DispatchState | None = None,
    binding: ProjectBinding | None = None,
    compaction_agent_runner: AgentAdapter | None = None,
) -> TickResult:
    """Dispatch a single Run to the semaphore-bounded slot.

    Acquires the semaphore, runs the full tick logic,
    and releases the slot on every exit path. The semaphore slot is held for
    the entire Run duration so the cap correctly blocks new dispatches when full.
    """
    state = dispatch_state or _new_dispatch_state(config)
    async with state.semaphore:
        try:
            result = await run_tick(
                config,
                adapter,
                agent_runner=agent_runner,
                render_prompt=render_prompt,
                compaction_agent_runner=compaction_agent_runner,
                notifier=notifier,
                run_blocked_reconciler=run_blocked_reconciler,
                dispatch_state=state,
                binding=binding,
            )
        except PlaneRateLimitError as exc:
            _record_rate_limit(state, exc)
            return TickResult(False, "plane-rate-limited")
        return result


async def reconcile_pending_review(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    dispatch_state: _DispatchState,
    *,
    notifier: TelegramNotifier | None = None,
) -> int:
    """Retry post-agent review transition after Plane rate-limit interruption."""

    if not dispatch_state.pending_review_issue_ids:
        return 0

    async with dispatch_state.in_flight_lock:
        in_flight_ids = set(dispatch_state.in_flight_ids)

    reconciled = 0
    for issue_id in tuple(dispatch_state.pending_review_issue_ids):
        if issue_id in in_flight_ids:
            continue
        issue = await _fetch_issue(adapter, issue_id)
        if not _is_state(
            issue,
            adapter.contract.state_name_for_role(TrackerRole.STATE_RUNNING),
            adapter.contract.state_value_for_role(TrackerRole.STATE_RUNNING),
        ):
            dispatch_state.pending_review_issue_ids.discard(issue_id)
            dispatch_state.pending_completion_bodies.pop(issue_id, None)
            continue
        issue_identifier = str(
            issue.get("sequence_id") or issue.get("identifier") or issue_id
        )
        comment_body = dispatch_state.pending_completion_bodies.get(issue_id)
        if comment_body:
            try:
                await adapter.add_comment(issue_id, CommentPayload(body=comment_body))
                dispatch_state.pending_completion_bodies.pop(issue_id, None)
            except PlaneRateLimitError:
                raise
        await adapter.transition_state(issue_id, TrackerRole.STATE_IN_REVIEW)
        LOGGER.info(
            "pending_review_reconciled issue_id=%s identifier=%s",
            issue_id,
            issue_identifier,
        )
        dispatch_state.pending_review_issue_ids.discard(issue_id)
        reconciled += 1
    return reconciled


async def reconcile_orphaned_runs(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    binding: ProjectBinding | None = None,
) -> int:
    """Reap durable Podium Run rows orphaned by scheduler restart."""

    reconcile = getattr(adapter, "reconcile_orphaned_runs", None)
    if not callable(reconcile):
        return 0
    timestamp = now().isoformat()
    resolved_binding = binding or _binding_from_config(config)
    binding_name = resolved_binding.name if resolved_binding is not None else ""
    LOGGER.info("run_reconcile_begin binding=%s", binding_name)
    reaped = int(await _maybe_await(reconcile(reaped_at=timestamp)))
    LOGGER.info("run_reconcile_done binding=%s reaped=%d", binding_name, reaped)
    return reaped


async def run_log_retention(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    binding: ProjectBinding | None = None,
) -> int:
    """Prune old Podium Run log files while keeping durable Run rows."""

    prune = getattr(adapter, "prune_run_logs", None)
    if not callable(prune):
        return 0
    resolved_binding = binding or _binding_from_config(config)
    binding_name = resolved_binding.name if resolved_binding is not None else ""
    now_dt = now()
    LOGGER.info("log_retention_begin binding=%s", binding_name)
    pruned = int(await _maybe_await(prune(now=now_dt)))
    LOGGER.info("log_retention_done binding=%s pruned=%d", binding_name, pruned)
    return pruned


async def reconcile_stale_running(
    adapter: TrackerAdapter,
    run_timeout_ms: int,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    dispatch_state: _DispatchState | None = None,
) -> None:
    """Reconcile Running issues whose durable claim comment is stale or interrupted."""

    in_flight_ids: set[str] = set()
    if dispatch_state is not None:
        async with dispatch_state.in_flight_lock:
            in_flight_ids = set(dispatch_state.in_flight_ids)

    interrupted_grace = timedelta(seconds=60)
    timeout_delta = timedelta(milliseconds=run_timeout_ms)
    for issue in await adapter.list_issues_by_state(
        TrackerRole.STATE_RUNNING,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    ):
        issue_id = str(issue["id"])
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is None:
            continue
        elapsed = now() - claim_time
        issue_name = str(issue.get("name", ""))
        issue_identifier = str(
            issue.get("sequence_id") or issue.get("identifier") or issue_id
        )
        if elapsed > timeout_delta:
            await _block_issue(
                adapter,
                issue_id,
                "Symphony claim timed out after scheduler restart",
                issue_name=issue_name,
                issue_identifier=issue_identifier,
                notifier=notifier,
            )
            continue
        if issue_id not in in_flight_ids and elapsed > interrupted_grace:
            await adapter.transition_state(issue_id, TrackerRole.STATE_IN_REVIEW)
            LOGGER.info(
                "state_transitioned issue_id=%s state=in-review reason=stale-running",
                issue_id,
            )


async def reconcile_startup(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    binding: ProjectBinding | None = None,
) -> int:
    """Reconcile startup state: recover Plane issues stuck in Running.

    Returns the number of items cleaned up. Runs before the main tick loop so
    the scheduler starts clean after a restart.
    """
    cleaned = 0

    cleaned += await reconcile_orphaned_runs(config, adapter, now=now, binding=binding)
    await run_log_retention(config, adapter, now=now, binding=binding)

    stale_running_issues: list[dict[str, Any]] = []
    for issue in await adapter.list_issues_by_state(
        TrackerRole.STATE_RUNNING,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    ):
        issue_id = str(issue["id"])
        identifier = str(
            issue.get("sequence_id") or issue.get("identifier") or issue_id
        )
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is not None and (now() - claim_time) <= timedelta(
            milliseconds=config.run_timeout_ms
        ):
            continue
        stale_running_issues.append(
            {
                "id": issue_id,
                "identifier": identifier,
                "name": issue.get("name", ""),
                "claim_time": claim_time,
            }
        )

    for issue in stale_running_issues:
        issue_url, dashboard_url = _build_urls(config, issue["id"])
        if issue["claim_time"] is None:
            message = "Symphony claim missing after scheduler restart"
        else:
            elapsed_ms = int((now() - issue["claim_time"]).total_seconds() * 1000)
            message = (
                f"Symphony claim timed out after scheduler restart "
                f"(claimed {elapsed_ms}ms ago, timeout={config.run_timeout_ms}ms)"
            )
        await _block_issue(
            adapter,
            issue["id"],
            message,
            issue_name=str(issue["name"]),
            issue_identifier=issue["identifier"],
            notifier=notifier,
            issue_url=issue_url,
            dashboard_url=dashboard_url,
        )
        cleaned += 1
        LOGGER.info(
            "reconcile_startup_reaped_issue issue_id=%s",
            issue["id"],
        )

    LOGGER.info("reconcile_startup_completed cleaned=%d", cleaned)
    return cleaned


async def _sleep_or_wake(
    timeout: float,
    *,
    sleep: Callable[[float], Any] | None = None,
    consume_wake: Callable[[], bool] | None = None,
    check_interval: float = WAKE_SENTINEL_CHECK_INTERVAL_S,
) -> bool:
    """Sleep up to ``timeout`` seconds, returning early when a wake is consumed."""

    sleep_fn = sleep or asyncio.sleep
    consume_fn = consume_wake or consume_wake_sentinel
    if consume_fn():
        return True
    remaining = max(0.0, timeout)
    while remaining > 0:
        delay = min(remaining, check_interval)
        await sleep_fn(delay)
        if consume_fn():
            return True
        remaining -= delay
    return False


async def _wait_for_tasks_or_wake(
    tasks: set[asyncio.Task[TickResult]],
    timeout: float,
) -> tuple[set[asyncio.Task[TickResult]], set[asyncio.Task[TickResult]], bool]:
    """Wait for a task completion or a wake sentinel, without busy-looping."""

    pending = set(tasks)
    remaining = max(0.0, timeout)
    if consume_wake_sentinel():
        return set(), pending, True
    while remaining > 0:
        delay = min(remaining, WAKE_SENTINEL_CHECK_INTERVAL_S)
        done, pending = await asyncio.wait(
            pending,
            timeout=delay,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if done:
            return set(done), set(pending), False
        if consume_wake_sentinel():
            return set(), set(pending), True
        remaining -= delay
    return set(), set(pending), False


async def run_loop(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    agent_runner: AgentAdapter,
    render_prompt: Callable[[CandidateIssue], str],
    notifier: TelegramNotifier | None = None,
    binding: ProjectBinding | None = None,
    compaction_agent_runner: AgentAdapter | None = None,
) -> None:
    """Run the concurrent dispatcher forever, sleeping between dispatches.

    The dispatcher launches up to run_cap Runs concurrently as async tasks.
    Each task holds its semaphore slot until the Run completes
    (on all exit paths — verdict, crash, timeout).
    Per-tick single-run serialization is removed; the semaphore cap is the only
    concurrency governor.
    """
    next_blocked_reconcile_at = datetime.now(UTC)
    next_log_retention_at = datetime.now(UTC) + LOG_RETENTION_INTERVAL
    active_tasks: set[asyncio.Task[TickResult]] = set()
    state = _DispatchState(
        semaphore=asyncio.Semaphore(config.run_cap),
        in_flight_ids=set(),
        in_flight_lock=asyncio.Lock(),
        poll_interval=config.poll_interval_ms / 1000,
    )

    while True:
        now_dt = datetime.now(UTC)
        run_blocked_reconcile = now_dt >= next_blocked_reconcile_at
        if now_dt >= next_log_retention_at:
            next_log_retention_at = now_dt + LOG_RETENTION_INTERVAL
            retention_kwargs = {"binding": binding} if binding is not None else {}
            await run_log_retention(
                config,
                adapter,
                now=_fixed_now(now_dt),
                **retention_kwargs,
            )

        # Reap completed tasks and propagate their log lines.
        done = {t for t in active_tasks if t.done()}
        for task in done:
            try:
                result = task.result()
            except Exception as exc:
                LOGGER.warning("dispatch_failed error=%s", exc, exc_info=True)
                continue
            LOGGER.info(
                "dispatch_completed dispatched=%s reason=%s issue_id=%s",
                str(result.dispatched).lower(),
                result.reason,
                result.issue_id or "",
            )
        active_tasks -= done
        cooldown_remaining = _cooldown_remaining_s(
            state, now=lambda now_dt=now_dt: now_dt
        )

        if run_blocked_reconcile:
            next_blocked_reconcile_at = now_dt + timedelta(
                milliseconds=config.blocked_reconciler_interval_ms
            )

        # Start one probe per poll cycle.  The probe may claim one candidate and
        # hold a semaphore slot for the whole Run.  Starting run_cap probes at
        # once duplicates Plane pagination/reconciler work while idle and can
        # trip Plane 429s; subsequent cycles fill remaining slots while long
        # Runs are active.
        slots_available = config.run_cap - len(active_tasks)
        if slots_available > 0 and cooldown_remaining <= 0:
            dispatch_kwargs: dict[str, Any] = {}
            if binding is not None:
                dispatch_kwargs["binding"] = binding
            if compaction_agent_runner is not None:
                dispatch_kwargs["compaction_agent_runner"] = compaction_agent_runner
            task = asyncio.create_task(
                _dispatch_one(
                    config,
                    adapter,
                    agent_runner,
                    render_prompt,
                    notifier,
                    run_blocked_reconcile,
                    state,
                    **dispatch_kwargs,
                )
            )
            active_tasks.add(task)

        wait_timeout = state.poll_interval
        if cooldown_remaining > 0 and not active_tasks:
            wait_timeout = min(wait_timeout, cooldown_remaining)

        if active_tasks:
            done_wait, pending, woke = await _wait_for_tasks_or_wake(
                active_tasks,
                wait_timeout,
            )
            if woke:
                LOGGER.info("wake_sentinel_consumed")
            all_idle = bool(done_wait)
            for task in done_wait:
                try:
                    result = task.result()
                except Exception as exc:
                    LOGGER.warning("dispatch_failed error=%s", exc, exc_info=True)
                    continue
                all_idle = all_idle and not result.dispatched
                LOGGER.info(
                    "dispatch_completed dispatched=%s reason=%s issue_id=%s",
                    str(result.dispatched).lower(),
                    result.reason,
                    result.issue_id or "",
                )
            active_tasks = set(pending)
            if woke:
                continue
            if not active_tasks and all_idle and await _sleep_or_wake(wait_timeout):
                LOGGER.info("wake_sentinel_consumed")
        else:
            if await _sleep_or_wake(wait_timeout):
                LOGGER.info("wake_sentinel_consumed")


async def _reserve_candidate(
    candidates: Sequence[CandidateIssue],
    contract: TrackerContract,
    *,
    approval_policy_enabled: bool,
    dispatch_state: _DispatchState | None = None,
) -> CandidateIssue | None:
    if dispatch_state is None:
        raise SchedulerError("dispatch_state is required")
    async with dispatch_state.in_flight_lock:
        available = [
            candidate
            for candidate in candidates
            if candidate.id not in dispatch_state.in_flight_ids
        ]
        selected = _oldest_candidate(
            available,
            contract,
            approval_policy_enabled=approval_policy_enabled,
        )
        if selected is not None:
            dispatch_state.in_flight_ids.add(selected.id)
        return selected


async def _reserve_specific_candidate(
    candidate: CandidateIssue,
    *,
    dispatch_state: _DispatchState | None = None,
) -> bool:
    if dispatch_state is None:
        raise SchedulerError("dispatch_state is required")
    async with dispatch_state.in_flight_lock:
        if candidate.id in dispatch_state.in_flight_ids:
            return False
        dispatch_state.in_flight_ids.add(candidate.id)
        return True


async def _release_candidate(
    issue_id: str,
    *,
    dispatch_state: _DispatchState | None = None,
) -> None:
    if dispatch_state is None:
        raise SchedulerError("dispatch_state is required")
    async with dispatch_state.in_flight_lock:
        dispatch_state.in_flight_ids.discard(issue_id)


def _oldest_candidate(
    candidates: Sequence[CandidateIssue],
    contract: TrackerContract = DEFAULT_CONTRACT,
    *,
    approval_policy_enabled: bool = True,
) -> CandidateIssue | None:
    eligible = [
        issue
        for issue in candidates
        if (
            not approval_policy_enabled
            or not _labels_contain_role(
                issue.labels, contract, TrackerRole.APPROVAL_REQUIRED
            )
        )
        and not _labels_contain_role(issue.labels, contract, TrackerRole.SCHEDULED)
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda issue: issue.created_at)[0]


async def _select_scheduled_candidate(
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime],
) -> _ScheduledSelection | None:
    label_ids = adapter.contract.label_ids if adapter.contract else None
    due: list[tuple[datetime, str, str, CandidateIssue, ScheduleEvent]] = []
    now_dt = now()

    issues = await adapter.list_issues_by_state(
        TrackerRole.STATE_TODO,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    )
    for issue in issues:
        labels = _extract_labels(issue, label_ids=label_ids)
        if not adapter.labels_contain_role(labels, TrackerRole.SCHEDULED):
            continue
        candidate = _candidate_from_issue(issue, labels=labels)
        try:
            event = await _latest_schedule_event(adapter, candidate.id)
        except ScheduleParseError as exc:
            return _ScheduledSelection(candidate, "scheduled-malformed", error=str(exc))
        if event is None:
            event = _default_scheduled_label_event(now_dt)
        if event.is_cancellation:
            return _ScheduledSelection(candidate, "scheduled-cancelled", event=event)
        if event.not_before is None:
            return _ScheduledSelection(
                candidate, "scheduled-malformed", error="not_before missing"
            )
        if event.not_before > now_dt:
            continue
        due.append(
            (event.not_before, candidate.created_at, candidate.id, candidate, event)
        )
    if not due:
        return None
    _, _, _, candidate, event = sorted(due, key=lambda item: item[:3])[0]
    return _ScheduledSelection(candidate, "scheduled-release", event=event)


def _with_schedule_context(
    candidate: CandidateIssue,
    event: ScheduleEvent | None,
    *,
    now: datetime,
) -> CandidateIssue:
    if event is None or event.not_before is None:
        return candidate
    late = bool(event.not_after and now.astimezone(UTC) > event.not_after)
    source = (
        SCHEDULED_LABEL_DEFAULT_SOURCE
        if event.raw_comment == SCHEDULED_LABEL_DEFAULT_SOURCE
        else "Symphony-Schedule comment"
    )
    return replace(
        candidate,
        schedule_not_before=event.not_before.isoformat(),
        schedule_not_after=event.not_after.isoformat() if event.not_after else "",
        schedule_reason=event.reason,
        schedule_source=source,
        schedule_late="true" if late else "false",
    )


def _default_scheduled_label_event(now_dt: datetime) -> ScheduleEvent:
    local_now = now_dt.astimezone(SCHEDULED_LABEL_WINDOW_TZ)
    if (
        SCHEDULED_LABEL_WINDOW_START_HOUR
        <= local_now.hour
        < SCHEDULED_LABEL_WINDOW_END_HOUR
    ):
        window_start = local_now.replace(
            hour=SCHEDULED_LABEL_WINDOW_START_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        next_day = local_now + timedelta(days=1)
        window_start = next_day.replace(
            hour=SCHEDULED_LABEL_WINDOW_START_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        )
    window_end = window_start.replace(hour=SCHEDULED_LABEL_WINDOW_END_HOUR)
    return ScheduleEvent(
        ScheduleEventType.SCHEDULE,
        SCHEDULED_LABEL_DEFAULT_REASON,
        not_before=window_start.astimezone(UTC),
        not_after=window_end.astimezone(UTC),
        raw_comment=SCHEDULED_LABEL_DEFAULT_SOURCE,
    )


def _response_items(
    response: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return response
    results = response.get("results")
    if isinstance(results, list):
        return results
    return []


async def _latest_schedule_event(
    adapter: TrackerAdapter, issue_id: str
) -> ScheduleEvent | None:
    comments: list[CandidateComment] = []
    for idx, comment in enumerate(await adapter.list_comments(issue_id)):
        created = _parse_optional_datetime(comment.get("created_at"))
        comments.append(
            CandidateComment(
                comment.get("body") or comment.get("comment_html") or "",
                comment_id=str(comment.get("id") or ""),
                created_at=created,
                api_order=idx,
            )
        )
    return latest_event(comments)


def _parse_optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def _release_scheduled_candidate(
    adapter: TrackerAdapter,
    issue_id: str,
    event: ScheduleEvent | None,
) -> ScheduleEvent:
    if event is None or event.not_before is None:
        raise SchedulerError("scheduled release missing event")
    latest = await _latest_schedule_event(adapter, issue_id)
    if latest is None and event.raw_comment == SCHEDULED_LABEL_DEFAULT_SOURCE:
        latest = event
    if latest is None:
        raise SchedulerError("latest schedule event disappeared before release")
    if latest.is_cancellation:
        raise SchedulerError("schedule was cancelled before release")
    if latest.not_before is None:
        raise SchedulerError("latest schedule event missing not_before")
    if (
        latest.not_before != event.not_before
        or latest.not_after != event.not_after
        or latest.reason != event.reason
    ):
        raise SchedulerError("schedule changed before release")
    await adapter.add_comment(
        issue_id,
        CommentPayload(
            body=(
                "Symphony scheduled release: not_before="
                f"{latest.not_before.isoformat()} reason={latest.reason}"
            )
        ),
    )
    await adapter.remove_labels(issue_id, [TrackerRole.SCHEDULED])
    return latest


async def _repair_cancelled_schedule(
    adapter: TrackerAdapter,
    issue_id: str,
    event: ScheduleEvent | None,
) -> None:
    reason = event.reason if event is not None else "unknown"
    await adapter.add_comment(
        issue_id,
        CommentPayload(
            body=f"Symphony schedule cancellation repaired stale scheduled label: {reason}"
        ),
    )
    await adapter.remove_labels(issue_id, [TrackerRole.SCHEDULED])


async def _detect_agent_schedule(
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    *,
    claim_dt: datetime,
    stdout: str,
    stderr: str,
    notifier: TelegramNotifier | None,
    config: SymphonyConfig | None = None,
) -> str | None:
    after_agent = await _fetch_issue(adapter, candidate.id)
    label_ids = adapter.contract.label_ids if adapter.contract else None
    labels = _extract_labels(after_agent, label_ids=label_ids)
    if not _is_state(
        after_agent,
        adapter.contract.state_name_for_role(TrackerRole.STATE_TODO),
        adapter.contract.state_value_for_role(TrackerRole.STATE_TODO),
    ):
        return None
    if not adapter.labels_contain_role(labels, TrackerRole.SCHEDULED):
        return None
    try:
        event = await _latest_schedule_event(adapter, candidate.id)
    except ScheduleParseError as exc:
        _iu, _du = _build_urls(config, candidate.id)
        await _block_issue(
            adapter,
            candidate.id,
            f"Agent created a malformed schedule comment: {exc}",
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return "agent-scheduled-malformed"
    if event is None or not event.is_schedule or event.comment_created_at is None:
        return None
    if event.comment_created_at <= claim_dt.astimezone(UTC):
        return None
    schedule_summary = _parse_summary_marker(stdout, stderr)
    body = "Symphony scheduled follow-up."
    if schedule_summary:
        body += f" {schedule_summary}"
    await adapter.add_comment(candidate.id, CommentPayload(body=body))
    return "agent-scheduled"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _fetch_issue(adapter: TrackerAdapter, issue_id: str) -> dict[str, Any]:
    return await adapter.get_issue(issue_id)


async def _fetch_issue_comments(adapter: TrackerAdapter, issue_id: str) -> str:
    comments = await adapter.list_comments(issue_id)
    comments.sort(key=lambda c: c.get("created_at", ""))
    parts: list[str] = []
    for comment in comments:
        body = str(comment.get("body") or comment.get("comment_html") or "").strip()
        if CLAIM_PREFIX in body or not body:
            continue
        created = comment.get("created_at", "")
        parts.append(f"**Comment ({created}):**\n{_format_previous_comment_body(body)}")
    return "\n\n---\n\n".join(parts)


async def _fetch_issue_comment_bodies(
    adapter: TrackerAdapter,
    issue_id: str,
    *,
    newest_first: bool = True,
) -> list[str]:
    comments = await adapter.list_comments(issue_id)
    comments.sort(key=lambda c: c.get("created_at", ""), reverse=newest_first)
    bodies: list[str] = []
    for comment in comments:
        body = str(comment.get("body") or comment.get("comment_html") or "")
        if CLAIM_PREFIX in body:
            continue
        body = body.strip()
        if not body:
            continue
        bodies.append(body)
    return bodies


async def _run_started_at(adapter: TrackerAdapter, issue_id: str) -> datetime | None:
    """Claim time from the latest Run record's ``started_at``, or None.

    Authoritative source since the claim comment was removed. Returns None for
    adapters without a Run store (e.g. Plane) so callers fall back to comments.
    """

    # Run records only exist on context-storing adapters (Podium). Gate on that
    # capability so Plane short-circuits here instead of paying a get_issue API
    # call on every reconcile tick (PlaneAdapter.get_run exists but returns None).
    if not getattr(adapter, "stores_context", False):
        return None
    get_run = getattr(adapter, "get_run", None)
    if not callable(get_run):
        return None
    try:
        issue = await adapter.get_issue(issue_id)
    except (KeyError, LookupError):
        return None
    run_id = str(issue.get("latest_run_id") or "")
    if not run_id:
        return None
    run = await _maybe_await(get_run(run_id))
    if not run:
        return None
    return _parse_iso(str(run.get("started_at") or ""))


async def _claimed_at(adapter: TrackerAdapter, issue_id: str) -> datetime | None:
    started = await _run_started_at(adapter, issue_id)
    if started is not None:
        return started
    claim_times: list[datetime] = []
    for comment in await adapter.list_comments(issue_id):
        body = str(comment.get("comment_html") or comment.get("body") or "")
        if CLAIM_PREFIX not in body:
            continue
        raw = body.split(CLAIM_PREFIX, 1)[1].strip().split()[0]
        try:
            claim_times.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    if not claim_times:
        return None
    return max(claim_times)


def _build_urls(config: SymphonyConfig | None, issue_id: str) -> tuple[str, str]:
    """Return (issue_url, dashboard_url) derived from config, or empty strings."""
    if config is None:
        return "", ""
    return config.issue_url(issue_id), config.plane_dashboard_url


async def _notify_review(
    notifier: TelegramNotifier | None,
    issue_name: str,
    issue_identifier: str,
    reason: str = "",
    *,
    issue_url: str = "",
    dashboard_url: str = "",
) -> None:
    if notifier is None:
        return
    try:
        await notifier.send(
            format_review_message(
                issue_name,
                issue_identifier,
                reason,
                issue_url=issue_url,
                dashboard_url=dashboard_url,
            )
        )
    except Exception as exc:
        LOGGER.warning("notification_error error=%s", exc)


async def _block_issue(
    adapter: TrackerAdapter,
    issue_id: str,
    message: str,
    *,
    issue_name: str = "",
    issue_identifier: str = "",
    notifier: TelegramNotifier | None = None,
    issue_url: str = "",
    dashboard_url: str = "",
) -> None:
    await adapter.add_comment(issue_id, CommentPayload(body=message))
    await adapter.transition_state(issue_id, TrackerRole.STATE_BLOCKED)
    LOGGER.info("state_transitioned issue_id=%s state=blocked", issue_id)
    if notifier:
        try:
            # The comment body can now be the agent's full ~4000-char summary;
            # bound it for the notifier so the Telegram message stays well under
            # the 4096-char limit (name/URL wrapping is added on top).
            notify_reason = message
            if len(notify_reason) > NOTIFY_REASON_MAX_CHARS:
                notify_reason = notify_reason[:NOTIFY_REASON_MAX_CHARS].rstrip() + "…"
            await notifier.send(
                format_blocked_message(
                    issue_name,
                    issue_identifier,
                    notify_reason,
                    issue_url=issue_url,
                    dashboard_url=dashboard_url,
                )
            )
        except Exception as exc:
            LOGGER.warning("notification_error issue_id=%s error=%s", issue_id, exc)
