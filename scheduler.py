"""Core Symphony scheduler loop."""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
import re
from collections.abc import Callable, Sequence
from importlib import import_module
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from agent_runner import AgentAdapter, AgentResult
from blocked_reconciler import reconcile_blocked
from code_version import resolve_code_sha
from config import SymphonyConfig
from notifier import (
    TelegramNotifier,
    format_blocked_message,
    format_review_message,
)

from plane_adapter import (
    CandidateIssue,
    CommentPayload,
    PlaneRateLimitError,
    TrackerAdapter,
)
from schedule import (
    CandidateComment,
    ScheduleEvent,
    ScheduleEventType,
    ScheduleParseError,
    latest_event,
)
from prompt_renderer import render_previous_comments_block
from tracker_contract import DEFAULT_CONTRACT, TrackerContract, TrackerRole
from web.api.db import resolve_run_log_root


LOGGER = logging.getLogger(__name__)
# Global semaphore capping live Runs. Retained for backward compat with
# tests that call run_tick / _dispatch_one directly via
# _fallback_dispatch_state(). Production path: each run_loop creates a
# per-binding _DispatchState with its own semaphore.
_RUN_SEMAPHORE: asyncio.Semaphore | None = None
_POLL_INTERVAL_S = 0.0  # retained for _fallback_dispatch_state
_IN_FLIGHT_ISSUE_IDS: set[str] = set()
_IN_FLIGHT_LOCK: asyncio.Lock | None = None
_PLANE_COOLDOWN_UNTIL: datetime | None = None
CLAIM_PREFIX = "Symphony claimed at "
# Resolved once at import time. The ``_claimed_at`` parser at line ~1212 splits
# the body on CLAIM_PREFIX and takes the first whitespace token after it, so
# appending ``code_sha=<sha>`` after the timestamp is backwards-compatible.
_CODE_SHA = resolve_code_sha()
REPORT_MAX_BYTES = 2048
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
    across all bindings.  Module-level globals still exist for backward compat
    with tests that call ``run_tick`` / ``_dispatch_one`` directly.

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


def _cooldown_remaining_s(
    state: _DispatchState,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> float:
    global _PLANE_COOLDOWN_UNTIL
    now_dt = now()
    remaining_values: list[float] = []
    if state.cooldown_until is not None:
        state_remaining = (state.cooldown_until - now_dt).total_seconds()
        if state_remaining <= 0:
            state.cooldown_until = None
        else:
            remaining_values.append(state_remaining)
    if _PLANE_COOLDOWN_UNTIL is not None:
        global_remaining = (_PLANE_COOLDOWN_UNTIL - now_dt).total_seconds()
        if global_remaining <= 0:
            _PLANE_COOLDOWN_UNTIL = None
        else:
            remaining_values.append(global_remaining)
    return max(remaining_values, default=0.0)


def _record_rate_limit(
    state: _DispatchState,
    exc: PlaneRateLimitError,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    jitter: Callable[[], float] = random.random,
) -> None:
    global _PLANE_COOLDOWN_UNTIL
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
    cooldown_until = now() + timedelta(seconds=delay_s)
    state.cooldown_until = cooldown_until
    if _PLANE_COOLDOWN_UNTIL is None or cooldown_until > _PLANE_COOLDOWN_UNTIL:
        _PLANE_COOLDOWN_UNTIL = cooldown_until
    LOGGER.warning(
        "plane_rate_limited cooldown_s=%.3f attempts=%s",
        delay_s,
        state.cooldown_attempts,
    )


def _clear_rate_limit(state: _DispatchState) -> None:
    global _PLANE_COOLDOWN_UNTIL
    state.cooldown_until = None
    state.cooldown_attempts = 0
    _PLANE_COOLDOWN_UNTIL = None


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


def _sanitize_report(text: str, secrets: Sequence[str]) -> str:
    report = _ANSI_ESCAPE_RE.sub("", text).strip()
    for secret in secrets:
        if secret:
            report = report.replace(secret, _REDACTED)
    encoded = report.encode("utf-8", errors="replace")
    if len(encoded) > REPORT_MAX_BYTES:
        # Keep the tail: failure context (final error, traceback footer) is
        # almost always more useful than the head of a long pi trace.
        tail = encoded[-REPORT_MAX_BYTES:].decode("utf-8", errors="replace")
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


def _format_timeline(
    claim_dt: datetime,
    now: Callable[[], datetime],
    *,
    duration_ms: int | None = None,
    verdict: str,
) -> str:
    """Render the terminal-state timeline appended to every closing comment.

    Compact one-line format using ISO-8601 UTC timestamps so log/diff tooling
    can correlate against ``Symphony claimed at <ts>`` claim comments without
    parsing prose.
    """
    finished_dt = now()
    delta_ms = int((finished_dt - claim_dt).total_seconds() * 1000)
    if duration_ms is not None and duration_ms > 0:
        agent_part = f"agent: {duration_ms}ms"
    else:
        agent_part = "agent: unmeasured"
    parts = [
        f"claimed: {claim_dt.isoformat()}",
        f"finished: {finished_dt.isoformat()}",
        agent_part,
        f"total: {delta_ms}ms",
        f"verdict: {verdict}",
        f"sha: {_CODE_SHA}",
    ]
    return "**Timeline** — " + " | ".join(parts)


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


def _extract_summary(result: AgentResult, secrets: Sequence[str]) -> str | None:
    """Pull SYMPHONY_SUMMARY from the raw streams and apply secret redaction.

    Summary extraction runs against the *unsanitized* stdout/stderr because
    `_sanitize_report` keeps only the last 2 KB of stderr (for failure-comment
    bounding); a summary line earlier in the stream would otherwise be lost.
    The captured line is still passed through ANSI stripping, whitespace
    collapse, and SUMMARY_MAX_CHARS truncation inside `_parse_summary_marker`.
    """

    summary = _parse_summary_marker(result.stdout, result.stderr)
    if summary is None:
        return None
    for secret in secrets:
        if secret:
            summary = summary.replace(secret, _REDACTED)
    return summary


def _write_run_log(log_path: Path, stdout: str, stderr: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"## stdout\n\n{stdout}\n\n## stderr\n\n{stderr}\n",
        encoding="utf-8",
    )


def _worktree_run_fields(
    config: SymphonyConfig, candidate: CandidateIssue, base_branch: str
) -> dict[str, str]:
    if not getattr(candidate, "worktree_active", False):
        return {}
    try:
        from web.api.worktree import branch_name, worktree_dir
    except ImportError:  # pragma: no cover - supports web/api import path
        from worktree import branch_name, worktree_dir  # type: ignore[no-redef]
    binding_name = getattr(candidate, "binding_name", "") or (
        config.bindings[0].name if config.bindings else ""
    )
    issue_id = str(candidate.id)
    return {
        "worktree_path": str(
            worktree_dir(config.homelab_repo_path, binding_name, issue_id)
        ),
        "branch_name": branch_name(binding_name, issue_id),
        "base_branch": base_branch,
    }


async def _maybe_compact_context(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    agent_runner: Callable[..., AgentResult],
    *,
    now: Callable[[], datetime],
) -> CandidateIssue:
    if not getattr(adapter, "stores_context", False):
        return candidate
    if not config.bindings:
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
            await _maybe_await(settings_fn(getattr(candidate, "binding_name", "") or config.bindings[0].name))
        )
    compaction = import_module("context_compaction")
    try:
        compacted = await asyncio.to_thread(
            vars(compaction)["maybe_compact"],
            candidate,
            config.bindings[0],
            agent_runner,
            threshold_tokens=int(settings["threshold_tokens"]),
            keep_recent_runs=int(settings["keep_recent_runs"]),
            now=now,
        )
    except Exception as exc:
        if isinstance(exc, vars(compaction)["ContextCompactionError"]):
            raise SchedulerContextCompactionError(str(exc)) from exc
        raise
    if compacted == str(getattr(candidate, "context_md", "") or ""):
        return candidate
    updated_issue = await _maybe_await(replace_context(candidate.id, compacted))
    return replace(
        candidate,
        context_md=str(updated_issue.get("context_md") or compacted),
    )


async def _start_run_record(
    adapter: TrackerAdapter,
    config: SymphonyConfig,
    candidate: CandidateIssue,
) -> tuple[str | None, Path | None]:
    if not getattr(adapter, "stores_context", False):
        return None, None
    record_run = getattr(adapter, "record_run", None)
    update_run = getattr(adapter, "update_run", None)
    if not callable(record_run) or not callable(update_run):
        return None, None
    binding = config.bindings[0] if config.bindings else None
    agent = binding.resolve_agent(candidate.labels) if binding is not None else "pi"
    base_branch = getattr(candidate, "base_branch", "") or config.base_branch
    run_payload = {
        "issue_id": candidate.id,
        "agent": agent,
        "provider": config.pi_provider,
        "model": config.pi_model,
        "state": "queued",
        "base_branch": base_branch,
        "skill_invoked": getattr(candidate, "preferred_skill", None),
        **_worktree_run_fields(config, candidate, base_branch),
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
    stdout: str,
    stderr: str,
    state: str,
    verdict: str | None,
    summary: str | None,
    ended_at: str,
) -> None:
    if not run_id or log_path is None:
        return
    _write_run_log(log_path, stdout, stderr)
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


class LockHeld(RuntimeError):
    """Raised when another scheduler owns the workspace lock."""


@dataclass(frozen=True)
class TickResult:
    dispatched: bool
    reason: str
    issue_id: str | None = None
    mode: str = "execute"


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


def _binding_approval_enabled(config: SymphonyConfig) -> bool:
    return bool(config.bindings and config.bindings[0].approval_policy.enabled)


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


async def run_tick(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    agent_runner: Callable[..., AgentResult],
    render_prompt: Callable[[CandidateIssue], str],
    lock_path: Path | None = None,
    poller: Callable[[TrackerAdapter], Any] | None = None,
    repo_dirty: Callable[[Path], bool] | None = None,
    diff_stat: Callable[[Path], str] | None = None,
    auto_commit: Callable[..., str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    run_blocked_reconciler: bool = True,
    dispatch_state: _DispatchState | None = None,
) -> TickResult:
    """Run one scheduler tick without sleeping forever."""

    is_coding = len(config.bindings) > 0 and config.bindings[0].binding_type == "coding"

    if dispatch_state is not None:
        await reconcile_pending_review(
            config, adapter, dispatch_state, notifier=notifier
        )

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
    if dispatch_state is not None:
        _clear_rate_limit(dispatch_state)

    approval_policy_enabled = _binding_approval_enabled(config) and not is_coding
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
        if not _is_state(fresh, adapter, TrackerRole.STATE_TODO):
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

        try:
            comments_text = await _fetch_issue_comments(adapter, candidate.id)
            candidate = await _maybe_compact_context(
                config,
                adapter,
                candidate,
                agent_runner,
                now=now,
            )
            prompt = render_prompt(candidate)
            if comments_text:
                prompt = f"{prompt}\n\n{render_previous_comments_block(comments_text)}"
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
            return TickResult(False, "context-compaction-failed", candidate.id, mode=mode)
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
            run_id, run_log_path = await _start_run_record(adapter, config, candidate)
            await adapter.transition_state(candidate.id, TrackerRole.STATE_RUNNING)
            claim_time = now().isoformat()
            await _mark_run_record_running(
                adapter,
                run_id,
                run_log_path,
                started_at=claim_time,
            )
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=f"{CLAIM_PREFIX}{claim_time}"),
            )
            claim_dt = datetime.fromisoformat(claim_time)
            LOGGER.info(
                "issue_claimed issue_id=%s claimed_at=%s", candidate.id, claim_time
            )

            secrets = _collect_secrets(config)

            try:
                result = await asyncio.to_thread(agent_runner, candidate, prompt)
            except Exception as exc:
                result = AgentResult(1, 0, False, stdout="", stderr=str(exc))
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    stdout="",
                    stderr=str(exc),
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

            LOGGER.info(
                "agent_exited issue_id=%s exit_code=%s duration_ms=%s timed_out=%s",
                candidate.id,
                result.exit_code,
                result.duration_ms,
                str(result.timed_out).lower(),
            )
            if result.timed_out:
                msg = f"Agent timed out after {result.duration_ms} ms"
                stdout, stderr = _format_report(result, secrets)
                summary = _extract_summary(result, secrets)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                msg += "\n\n" + _format_timeline(
                    claim_dt,
                    now,
                    duration_ms=result.duration_ms,
                    verdict="timeout",
                )
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    stdout=stdout,
                    stderr=stderr,
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
                summary = _extract_summary(result, secrets)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                msg += "\n\n" + _format_timeline(
                    claim_dt,
                    now,
                    duration_ms=result.duration_ms,
                    verdict="nonzero",
                )
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    stdout=stdout,
                    stderr=stderr,
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

            if _hit_permission_gate(stdout, stderr):
                msg = (
                    "Agent could not complete because required tool access was denied."
                )
                summary = _extract_summary(result, secrets)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    stdout=stdout,
                    stderr=stderr,
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

            if _hit_approval_gate(stdout, stderr):
                msg = "Agent could not complete because operator approval is required."
                summary = _extract_summary(result, secrets)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    stdout=stdout,
                    stderr=stderr,
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
            summary = _extract_summary(result, secrets)

            def _completion_body(verdict_label: str) -> str:
                if summary:
                    body = f"**Symphony completed:** {summary}"
                else:
                    body = "**Symphony completed:** Agent finished without a summary."
                body += "\n\n" + _format_timeline(
                    claim_dt,
                    now,
                    duration_ms=result.duration_ms,
                    verdict=verdict_label,
                )
                return body

            if verdict == "blocked":
                if summary:
                    msg = f"Agent reported a blocked result: {summary}"
                else:
                    msg = "Agent reported a blocked result."
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                msg += "\n\n" + _format_timeline(
                    claim_dt,
                    now,
                    duration_ms=result.duration_ms,
                    verdict="agent-marker-blocked",
                )
                await _finish_run_record(
                    adapter,
                    run_id,
                    run_log_path,
                    result=result,
                    stdout=stdout,
                    stderr=stderr,
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

            if not is_coding:
                after_agent = await _fetch_issue(adapter, candidate.id)
                if _is_state(after_agent, adapter, TrackerRole.STATE_IN_REVIEW):
                    return TickResult(True, "agent-review", candidate.id, mode=mode)
                if _is_state(after_agent, adapter, TrackerRole.STATE_BLOCKED):
                    return TickResult(True, "agent-blocked", candidate.id, mode=mode)

            reason_code = (
                "agent-marker-review"
                if verdict in {"review", "done"}
                else "agent-clean-review"
            )
            completion_body = _completion_body(reason_code)
            await _finish_run_record(
                adapter,
                run_id,
                run_log_path,
                result=result,
                stdout=stdout,
                stderr=stderr,
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
) -> TickResult:
    """Dispatch a single Run to the semaphore-bounded slot.

    Acquires the semaphore, runs the full tick logic,
    and releases the slot on every exit path. The semaphore slot is held for
    the entire Run duration so the cap correctly blocks new dispatches when full.
    """
    state = dispatch_state or _fallback_dispatch_state(config)
    async with state.semaphore:
        try:
            result = await run_tick(
                config,
                adapter,
                agent_runner=agent_runner,
                render_prompt=render_prompt,
                notifier=notifier,
                run_blocked_reconciler=run_blocked_reconciler,
                dispatch_state=state,
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
        if not _is_state(issue, adapter, TrackerRole.STATE_RUNNING):
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
) -> int:
    """Reap durable Podium Run rows orphaned by scheduler restart."""

    reconcile = getattr(adapter, "reconcile_orphaned_runs", None)
    if not callable(reconcile):
        return 0
    timestamp = now().isoformat()
    binding_name = config.bindings[0].name if config.bindings else ""
    LOGGER.info("run_reconcile_begin binding=%s", binding_name)
    reaped = int(await _maybe_await(reconcile(reaped_at=timestamp)))
    LOGGER.info("run_reconcile_done binding=%s reaped=%d", binding_name, reaped)
    return reaped


async def run_log_retention(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Prune old Podium Run log files while keeping durable Run rows."""

    prune = getattr(adapter, "prune_run_logs", None)
    if not callable(prune):
        return 0
    binding_name = config.bindings[0].name if config.bindings else ""
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
    config: SymphonyConfig | None = None,
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
) -> int:
    """Reconcile startup state: recover Plane issues stuck in Running.

    Returns the number of items cleaned up. Runs before the main tick loop so
    the scheduler starts clean after a restart.
    """
    cleaned = 0

    cleaned += await reconcile_orphaned_runs(config, adapter, now=now)
    await run_log_retention(config, adapter, now=now)

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


def init_run_semaphore(config: SymphonyConfig) -> None:
    """Create or replace the global live-run semaphore with the configured cap.

    Called once at startup and when the cap changes. Must be called before
    run_loop uses the semaphore.
    """
    global \
        _RUN_SEMAPHORE, \
        _POLL_INTERVAL_S, \
        _IN_FLIGHT_ISSUE_IDS, \
        _IN_FLIGHT_LOCK, \
        _PLANE_COOLDOWN_UNTIL
    _RUN_SEMAPHORE = asyncio.Semaphore(config.run_cap)
    _POLL_INTERVAL_S = config.poll_interval_ms / 1000
    _IN_FLIGHT_ISSUE_IDS = set()
    _IN_FLIGHT_LOCK = asyncio.Lock()
    _PLANE_COOLDOWN_UNTIL = None


def _fallback_dispatch_state(config: SymphonyConfig) -> _DispatchState:
    """Build a _DispatchState from module globals for backward compat.

    Used by tests and legacy callers that invoke _dispatch_one / run_tick
    without going through run_loop.
    """
    global _RUN_SEMAPHORE, _POLL_INTERVAL_S, _IN_FLIGHT_ISSUE_IDS, _IN_FLIGHT_LOCK
    if _RUN_SEMAPHORE is None:
        _RUN_SEMAPHORE = asyncio.Semaphore(config.run_cap)
    if _IN_FLIGHT_LOCK is None:
        _IN_FLIGHT_LOCK = asyncio.Lock()
    if _POLL_INTERVAL_S == 0.0:
        _POLL_INTERVAL_S = config.poll_interval_ms / 1000
    return _DispatchState(
        semaphore=_RUN_SEMAPHORE,
        in_flight_ids=_IN_FLIGHT_ISSUE_IDS,
        in_flight_lock=_IN_FLIGHT_LOCK,
        poll_interval=_POLL_INTERVAL_S,
    )


async def run_loop(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    agent_runner: AgentAdapter,
    render_prompt: Callable[[CandidateIssue], str],
    notifier: TelegramNotifier | None = None,
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
            await run_log_retention(
                config,
                adapter,
                now=_fixed_now(now_dt),
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
            task = asyncio.create_task(
                _dispatch_one(
                    config,
                    adapter,
                    agent_runner,
                    render_prompt,
                    notifier,
                    run_blocked_reconcile,
                    state,
                )
            )
            active_tasks.add(task)

        wait_timeout = state.poll_interval
        if cooldown_remaining > 0 and not active_tasks:
            wait_timeout = min(wait_timeout, cooldown_remaining)

        if active_tasks:
            done_wait, pending = await asyncio.wait(
                active_tasks,
                timeout=wait_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
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
            if not active_tasks and all_idle:
                await asyncio.sleep(wait_timeout)
        else:
            await asyncio.sleep(wait_timeout)


def _in_flight_lock() -> asyncio.Lock:
    global _IN_FLIGHT_LOCK
    if _IN_FLIGHT_LOCK is None:
        _IN_FLIGHT_LOCK = asyncio.Lock()
    return _IN_FLIGHT_LOCK


async def _reserve_candidate(
    candidates: Sequence[CandidateIssue],
    contract: TrackerContract,
    *,
    approval_policy_enabled: bool,
    dispatch_state: _DispatchState | None = None,
) -> CandidateIssue | None:
    lock = dispatch_state.in_flight_lock if dispatch_state else _in_flight_lock()
    ids = dispatch_state.in_flight_ids if dispatch_state else _IN_FLIGHT_ISSUE_IDS
    async with lock:
        available = [candidate for candidate in candidates if candidate.id not in ids]
        selected = _oldest_candidate(
            available,
            contract,
            approval_policy_enabled=approval_policy_enabled,
        )
        if selected is not None:
            ids.add(selected.id)
        return selected


async def _reserve_specific_candidate(
    candidate: CandidateIssue,
    *,
    dispatch_state: _DispatchState | None = None,
) -> bool:
    lock = dispatch_state.in_flight_lock if dispatch_state else _in_flight_lock()
    ids = dispatch_state.in_flight_ids if dispatch_state else _IN_FLIGHT_ISSUE_IDS
    async with lock:
        if candidate.id in ids:
            return False
        ids.add(candidate.id)
        return True


async def _release_candidate(
    issue_id: str,
    *,
    dispatch_state: _DispatchState | None = None,
) -> None:
    lock = dispatch_state.in_flight_lock if dispatch_state else _in_flight_lock()
    ids = dispatch_state.in_flight_ids if dispatch_state else _IN_FLIGHT_ISSUE_IDS
    async with lock:
        ids.discard(issue_id)


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


def _next_cursor(response: dict[str, Any] | list[dict[str, Any]]) -> str | None:
    if not isinstance(response, dict):
        return None
    cursor = response.get("next_cursor")
    if cursor:
        return str(cursor)
    next_url = response.get("next")
    if isinstance(next_url, str) and "cursor=" in next_url:
        return next_url.split("cursor=", 1)[1].split("&", 1)[0]
    return None


def _candidate_from_issue(
    issue: dict[str, Any], *, labels: tuple[str, ...]
) -> CandidateIssue:
    issue_id = str(issue.get("id", ""))
    identifier = str(issue.get("sequence_id") or issue.get("identifier") or issue_id)
    return CandidateIssue(
        issue_id,
        identifier,
        str(issue.get("name") or ""),
        str(issue.get("description_html") or issue.get("description") or ""),
        labels,
        str(issue.get("created_at") or ""),
    )


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
    if not _is_state(after_agent, adapter, TrackerRole.STATE_TODO):
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


async def _claimed_at(adapter: TrackerAdapter, issue_id: str) -> datetime | None:
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
            await notifier.send(
                format_blocked_message(
                    issue_name,
                    issue_identifier,
                    message,
                    issue_url=issue_url,
                    dashboard_url=dashboard_url,
                )
            )
        except Exception as exc:
            LOGGER.warning("notification_error issue_id=%s error=%s", issue_id, exc)


def _is_state(
    issue: dict[str, Any], adapter: TrackerAdapter, state: TrackerRole
) -> bool:
    current = issue.get("state")
    state_name = adapter.contract.state_name_for_role(state)
    wanted = {state_name, adapter.contract.state_value_for_role(state)}
    if isinstance(current, str):
        return current in wanted
    if isinstance(current, dict):
        return current.get("name") == state_name or current.get("id") in wanted
    return False


def _extract_labels(
    issue: dict[str, Any],
    label_ids: dict[str, str] | None = None,
) -> tuple[str, ...]:
    labels = issue.get("labels") or []
    uuid_to_name: dict[str, str] = {}
    if label_ids:
        uuid_to_name = {v: k for k, v in label_ids.items()}
    names: list[str] = []
    for label in labels:
        if isinstance(label, str):
            names.append(uuid_to_name.get(label, label))
        elif isinstance(label, dict):
            name = label.get("name") or label.get("value")
            if isinstance(name, str):
                names.append(name)
    return tuple(names)
