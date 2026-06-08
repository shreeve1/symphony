"""Core Symphony scheduler loop."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Sequence
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
from run_worktree import (
    create_worktree,
    kill_tmux_session,
    list_worktrees,
    remove_worktree,
    remove_worktree_if_exists,
    _run_id_from_identifier,
    _run_id_from_worktree_path,
    worktree_branch,
    worktree_path,
)
from schedule import CandidateComment, ScheduleEvent, ScheduleEventType, ScheduleParseError, latest_event

from plane_adapter import CandidateIssue, CommentPayload, TrackerAdapter
from tracker_contract import DEFAULT_CONTRACT, TrackerContract, TrackerRole
from prompt_renderer import render_previous_comments_block


LOGGER = logging.getLogger(__name__)
# Global semaphore capping live Runs. Retained for backward compat with
# tests that call run_tick / _dispatch_one directly via
# _fallback_dispatch_state(). Production path: each run_loop creates a
# per-binding _DispatchState with its own semaphore.
_RUN_SEMAPHORE: asyncio.Semaphore = None  # type: ignore[assignment]
_POLL_INTERVAL_S = 0.0  # retained for _fallback_dispatch_state
_IN_FLIGHT_ISSUE_IDS: set[str] = set()
_IN_FLIGHT_LOCK: asyncio.Lock | None = None
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
SCHEDULED_LABEL_WINDOW_TZ = ZoneInfo("America/Los_Angeles")
SCHEDULED_LABEL_WINDOW_START_HOUR = 0
SCHEDULED_LABEL_WINDOW_END_HOUR = 6
SCHEDULED_LABEL_DEFAULT_REASON = "scheduled label maintenance window"
SCHEDULED_LABEL_DEFAULT_SOURCE = "scheduled label maintenance window (12am-6am PT)"
_REDACTED = "***REDACTED***"
_PLAN_HANDOFF_MARKER = "Symphony completed plan."


@dataclass(frozen=True)
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


def _hit_permission_gate(stdout: str, stderr: str) -> bool:
    """Return true when the executor clean-exited after denied tool access."""

    return bool(_PERMISSION_GATE_RE.search(f"{stdout}\n{stderr}"))


def _hit_approval_gate(stdout: str, stderr: str) -> bool:
    """Return true when a clean exit still needs operator approval."""

    return bool(_APPROVAL_GATE_RE.search(f"{stdout}\n{stderr}"))


class SchedulerError(RuntimeError):
    """Raised for scheduler setup failures."""


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


def _format_report(
    result: AgentResult, secrets: Sequence[str]
) -> tuple[str, str]:
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

    Symphony tickets currently lack a single human-readable summary of when
    the agent claimed the issue, when it released it, how long it ran, and
    what verdict carried it across. AUTO-98 made this gap visible: a Blocked
    ticket with no audit trail of which Symphony run reached the failure.

    The block is intentionally compact — three lines — and uses ISO-8601 UTC
    timestamps so log/diff tooling can correlate against
    ``Symphony claimed at <ts> code_sha=<sha>`` claim comments without
    parsing prose.
    """
    finished_dt = now()
    delta_ms = int((finished_dt - claim_dt).total_seconds() * 1000)
    if duration_ms is not None and duration_ms > 0:
        agent_line = f"- agent_duration_ms: {duration_ms}"
    else:
        agent_line = "- agent_duration_ms: (not measured)"
    return (
        "**Timeline**\n"
        f"- claimed_at: {claim_dt.isoformat()}\n"
        f"- finished_at: {finished_dt.isoformat()}\n"
        f"- claim_to_finish_ms: {delta_ms}\n"
        f"{agent_line}\n"
        f"- verdict: {verdict}\n"
        f"- code_sha: {_CODE_SHA}"
    )


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
    first_line = next((line.strip() for line in stripped.splitlines() if line.strip()), "Previous comment")
    if len(first_line) > 180:
        first_line = first_line[:179].rstrip() + "…"
    tail = stripped[-PREVIOUS_COMMENT_TAIL_CHARS:].strip()
    return (
        f"{first_line}\n\n"
        f"[Previous comment truncated from {len(stripped)} characters for Symphony prompt readability.]\n\n"
        f"{tail}"
    )


def _extract_summary(
    result: AgentResult, secrets: Sequence[str]
) -> str | None:
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
    contract: TrackerContract,
    role: TrackerRole,
) -> bool:
    binding = contract.optional_label_binding(role)
    if binding is None:
        return False
    values = {binding.name}
    if binding.uuid:
        values.add(binding.uuid)
    return bool(values & set(labels))


def _resolve_mode(
    labels: tuple[str, ...],
    contract: TrackerContract = DEFAULT_CONTRACT,
) -> str:
    if _labels_contain_role(labels, contract, TrackerRole.MODE_BUILD):
        return "build"
    if _labels_contain_role(labels, contract, TrackerRole.MODE_PLAN):
        return "plan"
    return "execute"


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


def _validate_issue_plan_path(repo_path: Path, issue: CandidateIssue, raw_path: str) -> Path:
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


def _validated_fallback_plan_path(repo_path: Path, issue: CandidateIssue) -> Path | None:
    expected = _expected_plan_path(repo_path, issue)
    try:
        return _validate_issue_plan_path(repo_path, issue, str(expected))
    except ValueError:
        return None


def _validate_plan_branch_ref(repo_path: Path, raw_ref: str) -> str:
    ref = raw_ref.strip()
    if not ref or ref.startswith("/") or ref.startswith("-") or re.search(r"\s", ref):
        raise ValueError("plan handoff is not a branch ref")
    check = subprocess.run(
        ["git", "check-ref-format", "--branch", ref],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise ValueError("plan handoff is not a valid branch ref")
    exists = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{ref}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if exists.returncode != 0:
        raise ValueError("plan handoff branch ref does not exist")
    return ref


def _plan_path_from_comments(repo_path: Path, issue: CandidateIssue, comments: list[str]) -> tuple[str | None, str | None]:
    for body in comments:
        if _PLAN_HANDOFF_MARKER not in body:
            continue
        final_line = _final_non_empty_line(body)
        if not final_line:
            continue
        try:
            return _validate_plan_branch_ref(repo_path, final_line), None
        except ValueError as exc:
            return None, str(exc)
    return None, None


def _is_git_repo(path: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _invoke_agent_runner(
    agent_runner: Callable[..., AgentResult],
    candidate: CandidateIssue,
    prompt: str,
    *,
    worktree_path: Path | None,
) -> AgentResult:
    try:
        return agent_runner(candidate, prompt, worktree_path=worktree_path)
    except TypeError as exc:
        if "worktree_path" not in str(exc):
            raise
        return agent_runner(candidate, prompt)


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
    """Run one scheduler tick without sleeping forever.

    Design retro — worktree-cleanliness gate (Phase 4 #5)
    ----------------------------------------------------
    Prior versions of Symphony refused to dispatch (and refused to
    auto-commit) when the homelab worktree was dirty. The gate caused
    repeated false blocks: any unrelated half-staged edit on aidev would
    park the entire ticket queue. Commit ``80125f6`` removed the gate
    and made post-agent auto-commit best-effort: if the commit fails,
    the ticket still closes Done/In Review/Blocked, but the closing
    comment carries a ``WARNING: Symphony auto-commit failed`` block
    naming the error and (when available) a pending diff stat.

    Consequence: ``repo_dirty`` is no longer a gating signal. It is
    threaded in only so the auto-commit path can decide *whether* to
    run, not whether the ticket may proceed. The historical contract
    ("dirty worktree → IN_REVIEW transition") has been replaced by a
    softer contract ("dirty worktree → attempt commit, warn on
    failure"). Any future change that wants to re-introduce gating
    must do so via an explicit, named policy rather than by silently
    coupling worktree state to dispatch eligibility.
    """

    repo_dirty = _repo_dirty if repo_dirty is None else repo_dirty
    diff_stat = _diff_stat if diff_stat is None else diff_stat
    auto_commit = _auto_commit if auto_commit is None else auto_commit

    # reconcile_stale_running and reconcile_blocked run every tick, outside
    # the semaphore, so they are not blocked by an in-flight Run.
    await reconcile_stale_running(adapter, config.run_timeout_ms, now=now, notifier=notifier, config=config)
    if config.blocked_reconciler_enabled and run_blocked_reconciler:
        try:
            await reconcile_blocked(
                adapter,
                apply=config.blocked_reconciler_apply,
                now=now,
            )
        except Exception as exc:
            LOGGER.warning(
                "blocked_reconcile_failed error=%s", exc, exc_info=True
            )
    scheduled_reserved = False
    scheduled = await _select_scheduled_candidate(adapter, now=now)
    if scheduled is not None:
        if scheduled.reason == "scheduled-release":
            candidate = scheduled.candidate
            if not await _reserve_specific_candidate(candidate, dispatch_state=dispatch_state):
                return TickResult(False, "already-in-flight", candidate.id)
            scheduled_reserved = True
            try:
                released_event = await _release_scheduled_candidate(adapter, candidate.id, scheduled.event)
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
                    await _release_candidate(candidate.id, dispatch_state=dispatch_state)
                    scheduled_reserved = False
                return TickResult(False, "scheduled-release-failed", candidate.id)
            candidate = _with_schedule_context(scheduled.candidate, released_event, now=now())
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
            await _repair_cancelled_schedule(adapter, scheduled.candidate.id, scheduled.event)
            return TickResult(False, "scheduled-cancelled", scheduled.candidate.id)
        else:
            candidate = None
    else:
        candidate = None

    try:
        candidates = [] if candidate is not None else await _maybe_await(
            poller(adapter) if poller is not None else adapter.list_candidates()
        )
    except Exception as exc:
        LOGGER.warning("plane_poll_failed error=%s", exc)
        return TickResult(False, "plane-unreachable")

    approval_policy_enabled = _binding_approval_enabled(config)
    if candidate is None:
        candidate = await _reserve_candidate(
            candidates,
            adapter.contract,
            approval_policy_enabled=approval_policy_enabled,
            dispatch_state=dispatch_state,
        )
    elif not scheduled_reserved and not await _reserve_specific_candidate(
        candidate, dispatch_state=dispatch_state,
    ):
        return TickResult(False, "already-in-flight", candidate.id)
    if candidate is None:
        return TickResult(False, "no-candidates")

    try:
        if approval_policy_enabled and adapter.labels_contain_role(candidate.labels, TrackerRole.APPROVAL_REQUIRED):
            return TickResult(False, "approval-required", candidate.id)

        mode = _resolve_mode(candidate.labels, adapter.contract)

        fresh = await _fetch_issue(adapter, candidate.id)
        if not _is_state(fresh, adapter, TrackerRole.STATE_TODO):
            return TickResult(False, "state-changed", candidate.id)
        label_ids = adapter.contract.label_ids if adapter.contract else None
        fresh_labels = _extract_labels(fresh, label_ids=label_ids)
        if approval_policy_enabled and adapter.labels_contain_role(fresh_labels, TrackerRole.APPROVAL_REQUIRED):
            return TickResult(False, "approval-required", candidate.id)

        if adapter.labels_contain_role(fresh_labels, TrackerRole.SCHEDULED):
            return TickResult(False, "scheduled-held", candidate.id)

        plan_path: Path | None = None
        plan_branch_ref: str | None = None
        if mode == "build":
            if adapter.labels_contain_role(fresh_labels, TrackerRole.MODE_PLAN):
                try:
                    await adapter.remove_labels(candidate.id, [TrackerRole.MODE_PLAN])
                except Exception as exc:
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(body=f"Build could not start: failed to remove stale `plan` label: {exc}"),
                    )
                    return TickResult(False, "stale-plan-label-remove-failed", candidate.id, mode=mode)

            comment_bodies = await _fetch_issue_comment_bodies(adapter, candidate.id)
            plan_branch_ref, plan_branch_error = _plan_path_from_comments(
                config.homelab_repo_path, candidate, comment_bodies
            )
            if plan_branch_error:
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter,
                    candidate.id,
                    f"Build could not start: {plan_branch_error}.",
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(False, "invalid-plan-branch", candidate.id, mode=mode)
            if plan_branch_ref is None:
                plan_path = _validated_fallback_plan_path(config.homelab_repo_path, candidate)
            if plan_branch_ref is None and plan_path is None:
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
                    return TickResult(False, "build-plan-recovery-failed", candidate.id, mode=mode)
                return TickResult(False, "build-plan-missing-returned-to-plan", candidate.id, mode=mode)

        try:
            comments_text = await _fetch_issue_comments(adapter, candidate.id)
            prompt = render_prompt(candidate)
            if comments_text:
                prompt = f"{prompt}\n\n{render_previous_comments_block(comments_text)}"
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

        run_id = _run_id_from_identifier(candidate.identifier)
        wt_path: Path | None = None
        run_repo = config.homelab_repo_path
        try:
            if _is_git_repo(config.homelab_repo_path):
                remove_worktree_if_exists(config, run_id)
                wt_path = create_worktree(config, run_id, base_branch=plan_branch_ref or config.base_branch)
                run_repo = wt_path
                LOGGER.info(
                    "run_worktree_created issue_id=%s run_id=%s path=%s",
                    candidate.id, run_id, wt_path,
                )

            if mode == "build" and plan_branch_ref is not None:
                try:
                    plan_path = _validate_issue_plan_path(
                        run_repo,
                        candidate,
                        str(_expected_plan_path(run_repo, candidate)),
                    )
                except ValueError as exc:
                    _iu, _du = _build_urls(config, candidate.id)
                    await _block_issue(
                        adapter,
                        candidate.id,
                        f"Build could not start: plan handoff branch `{plan_branch_ref}` did not contain a readable plan file: {exc}.",
                        issue_name=candidate.name,
                        issue_identifier=candidate.identifier,
                        notifier=notifier,
                        issue_url=_iu,
                        dashboard_url=_du,
                    )
                    return TickResult(False, "invalid-plan-branch-plan", candidate.id, mode=mode)

            # repo_dirty / diff_stat / auto_commit operate in the run worktree
            # when one exists, so commits land on the run branch, never the
            # shared checkout.
            _wt: Path = run_repo
            _repo_dirty_wt = lambda: repo_dirty(_wt)
            _diff_stat_wt = lambda: diff_stat(_wt)
            _auto_commit_wt: Callable[..., str] = lambda *a, **kw: auto_commit(_wt, *a, **kw)

            await adapter.transition_state(candidate.id, TrackerRole.STATE_RUNNING)
            claim_time = now().isoformat()
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=f"{CLAIM_PREFIX}{claim_time} code_sha={_CODE_SHA}"),
            )
            claim_dt = datetime.fromisoformat(claim_time)
            LOGGER.info("issue_claimed issue_id=%s claimed_at=%s", candidate.id, claim_time)

            secrets = _collect_secrets(config)

            try:
                result = await asyncio.to_thread(
                    _invoke_agent_runner,
                    candidate=candidate,
                    prompt=prompt,
                    agent_runner=agent_runner,
                    worktree_path=wt_path,
                )
            except Exception as exc:
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter, candidate.id, f"Agent crashed: {exc}",
                    issue_name=candidate.name, issue_identifier=candidate.identifier,
                    notifier=notifier, issue_url=_iu, dashboard_url=_du,
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
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                msg += "\n\n" + _format_timeline(
                    claim_dt, now,
                    duration_ms=result.duration_ms,
                    verdict="timeout",
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter, candidate.id, msg,
                    issue_name=candidate.name, issue_identifier=candidate.identifier,
                    notifier=notifier, issue_url=_iu, dashboard_url=_du,
                )
                return TickResult(True, "timeout", candidate.id, mode=mode)
            if result.exit_code != 0:
                msg = f"Agent failed with exit code {result.exit_code} after {result.duration_ms} ms"
                stdout, stderr = _format_report(result, secrets)
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                msg += "\n\n" + _format_timeline(
                    claim_dt, now,
                    duration_ms=result.duration_ms,
                    verdict="nonzero",
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _block_issue(
                    adapter, candidate.id, msg,
                    issue_name=candidate.name, issue_identifier=candidate.identifier,
                    notifier=notifier, issue_url=_iu, dashboard_url=_du,
                )
                return TickResult(True, "nonzero", candidate.id, mode=mode)

            stdout, stderr = _format_report(result, secrets)

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
                return TickResult(True, scheduled_after_agent, candidate.id, mode=mode)

            if _hit_permission_gate(stdout, stderr):
                msg = "Agent could not complete because required tool access was denied."
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
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
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
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

            if mode == "plan":
                plan_report_path = _final_non_empty_line(stdout) if stdout else None
                if plan_report_path and plan_report_path.startswith("/"):
                    try:
                        plan_report_path = str(
                            _validate_issue_plan_path(
                                _wt,
                                candidate,
                                plan_report_path,
                            )
                        )
                    except ValueError:
                        plan_report_path = None
                else:
                    plan_report_path = None

                if plan_report_path and wt_path is not None and _repo_dirty_wt():
                    try:
                        _auto_commit_wt(
                            issue_identifier=candidate.identifier,
                            issue_name=candidate.name,
                            issue_id=candidate.id,
                            plan_path=plan_report_path,
                        )
                    except AutoCommitFailed as exc:
                        _iu, _du = _build_urls(config, candidate.id)
                        await _block_issue(
                            adapter,
                            candidate.id,
                            f"Plan mode could not commit the handoff artifact to `{worktree_branch(run_id)}`: {exc}",
                            issue_name=candidate.name,
                            issue_identifier=candidate.identifier,
                            notifier=notifier,
                            issue_url=_iu,
                            dashboard_url=_du,
                        )
                        return TickResult(True, "plan-commit-failed", candidate.id, mode=mode)

                plan_summary = _extract_summary(result, secrets)
                body = _PLAN_HANDOFF_MARKER
                if plan_summary:
                    body += f" {plan_summary}"
                body += f"\n\n{worktree_branch(run_id)}"
                await adapter.add_comment(
                    candidate.id,
                    CommentPayload(body=body),
                )
                if approval_policy_enabled and adapter.contract.optional_label_binding(TrackerRole.APPROVAL_REQUIRED) is not None:
                    await adapter.add_labels(
                        candidate.id, [TrackerRole.APPROVAL_REQUIRED]
                    )
                await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
                LOGGER.info("state_transitioned issue_id=%s state=in-review mode=plan", candidate.id)
                _iu, _du = _build_urls(config, candidate.id)
                await _notify_review(
                    notifier, candidate.name, candidate.identifier,
                    reason="Plan mode completed, awaiting approval",
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "plan", candidate.id, mode=mode)

            committed_sha: str | None = None
            committed_stat: str | None = None
            auto_commit_error: str | None = None
            if _repo_dirty_wt():
                committed_stat = _diff_stat_wt()
                try:
                    committed_sha = _auto_commit_wt(
                        issue_identifier=candidate.identifier,
                        issue_name=candidate.name,
                        issue_id=candidate.id,
                        plan_path=str(plan_path) if plan_path else None,
                    )
                except AutoCommitFailed as exc:
                    LOGGER.warning(
                        "auto_commit_failed issue_id=%s repo=%s error=%s",
                        candidate.id, wt_path, exc,
                    )
                    auto_commit_error = str(exc)
                    if exc.stderr:
                        auto_commit_error += (
                            f"\n\n**git stderr:**\n```\n{_sanitize_report(exc.stderr, secrets)}\n```"
                        )
                else:
                    LOGGER.info(
                        "auto_commit_succeeded issue_id=%s sha=%s",
                        candidate.id, committed_sha,
                    )

            def _auto_commit_warning_body() -> str:
                body = f"**WARNING: Symphony auto-commit failed:** {auto_commit_error}"
                if committed_stat and committed_stat != "No diff stat available":
                    body += (
                        f"\n\n**Pending diff stat:**\n```\n{committed_stat}\n```"
                    )
                return body

            after_agent = await _fetch_issue(adapter, candidate.id)
            if _is_state(after_agent, adapter, TrackerRole.STATE_DONE):
                if auto_commit_error is not None:
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(body=_auto_commit_warning_body()),
                    )
                return TickResult(True, "agent-done", candidate.id, mode=mode)
            if _is_state(after_agent, adapter, TrackerRole.STATE_IN_REVIEW):
                if auto_commit_error is not None:
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(body=_auto_commit_warning_body()),
                    )
                return TickResult(True, "agent-review", candidate.id, mode=mode)
            if _is_state(after_agent, adapter, TrackerRole.STATE_BLOCKED):
                if auto_commit_error is not None:
                    await adapter.add_comment(
                        candidate.id,
                        CommentPayload(body=_auto_commit_warning_body()),
                    )
                return TickResult(True, "agent-blocked", candidate.id, mode=mode)

            # No repo changes, no in-agent state transition. Resolve the
            # agent's verdict from an explicit SYMPHONY_RESULT marker in
            # stdout, or fall through to a clean-exit Done.
            verdict = _parse_result_marker(stdout)
            summary = _extract_summary(result, secrets)

            def _completion_body(verdict_label: str) -> str:
                if summary:
                    body = f"**Symphony completed:** {summary}"
                else:
                    body = "**Symphony completed:**"
                if committed_sha is not None:
                    commit_block = (
                        f"\n\n**Symphony auto-committed changes:** `{committed_sha}`"
                    )
                    if committed_stat and committed_stat != "No diff stat available":
                        commit_block += f"\n\n```\n{committed_stat}\n```"
                    body += commit_block
                elif auto_commit_error is not None:
                    body += (
                        f"\n\n**WARNING: Symphony auto-commit failed:** {auto_commit_error}"
                    )
                    if committed_stat and committed_stat != "No diff stat available":
                        body += f"\n\n**Pending diff stat:**\n```\n{committed_stat}\n```"
                body += "\n\n" + _format_timeline(
                    claim_dt, now,
                    duration_ms=result.duration_ms,
                    verdict=verdict_label,
                )
                return body

            if verdict == "blocked":
                if summary:
                    msg = f"Agent reported a blocked result: {summary}"
                else:
                    msg = "Agent reported a blocked result."
                if committed_sha is not None:
                    msg += (
                        f"\n\n**Symphony auto-committed changes:** `{committed_sha}`"
                    )
                    if committed_stat and committed_stat != "No diff stat available":
                        msg += f"\n\n```\n{committed_stat}\n```"
                elif auto_commit_error is not None:
                    msg += (
                        f"\n\n**WARNING: Symphony auto-commit failed:** {auto_commit_error}"
                    )
                    if committed_stat and committed_stat != "No diff stat available":
                        msg += f"\n\n**Pending diff stat:**\n```\n{committed_stat}\n```"
                if stderr:
                    msg += f"\n\n{_format_stderr_summary(stderr)}"
                msg += "\n\n" + _format_timeline(
                    claim_dt, now,
                    duration_ms=result.duration_ms,
                    verdict="agent-marker-blocked",
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

            if verdict == "review":
                await adapter.add_comment(
                    candidate.id,
                    CommentPayload(body=_completion_body("agent-marker-review")),
                )
                await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
                LOGGER.info(
                    "state_transitioned issue_id=%s state=in-review reason=marker",
                    candidate.id,
                )
                _iu, _du = _build_urls(config, candidate.id)
                await _notify_review(
                    notifier, candidate.name, candidate.identifier,
                    reason="Agent reported SYMPHONY_RESULT: review",
                    issue_url=_iu,
                    dashboard_url=_du,
                )
                return TickResult(True, "agent-marker-review", candidate.id, mode=mode)

            # verdict == "done" or no marker: trust clean exit and mark Done.
            reason_code = "agent-marker-done" if verdict == "done" else "agent-clean-done"
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=_completion_body(reason_code)),
            )
            await adapter.transition_state(candidate.id, TrackerRole.STATE_DONE)
            LOGGER.info(
                "state_transitioned issue_id=%s state=done reason=%s",
                candidate.id, reason_code,
            )
            return TickResult(True, reason_code, candidate.id, mode=mode)
        finally:
            # Guaranteed cleanup: remove worktree and any detached tmux session
            # on every exit path so no orphan is left behind after verdict
            # reconciliation, crash, timeout, or task cancellation.
            if wt_path is not None:
                remove_worktree_if_exists(config, run_id)
            kill_tmux_session(run_id)

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
    """Dispatch a single Run to the semaphore-bounded worktree slot.

    Acquires the semaphore, runs the full tick logic with worktree lifecycle,
    and releases the slot on every exit path. The semaphore slot is held for
    the entire Run duration so the cap correctly blocks new dispatches when full.
    """
    state = dispatch_state or _fallback_dispatch_state(config)
    async with state.semaphore:
        return await run_tick(
            config,
            adapter,
            agent_runner=agent_runner,
            render_prompt=render_prompt,
            notifier=notifier,
            run_blocked_reconciler=run_blocked_reconciler,
            dispatch_state=state,
        )


async def reconcile_stale_running(
    adapter: TrackerAdapter,
    run_timeout_ms: int,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    config: SymphonyConfig | None = None,
) -> None:
    """Block Running issues whose durable claim comment is stale."""

    for issue in await adapter.list_issues_by_state(
        TrackerRole.STATE_RUNNING,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    ):
        issue_id = str(issue["id"])
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is None:
            continue
        if now() - claim_time > timedelta(milliseconds=run_timeout_ms):
            issue_name = str(issue.get("name", ""))
            issue_identifier = str(issue.get("sequence_id") or issue.get("identifier") or issue_id)
            issue_url, dashboard_url = _build_urls(config, issue_id)
            await _block_issue(
                adapter, issue_id, "Symphony claim timed out after scheduler restart",
                issue_name=issue_name, issue_identifier=issue_identifier,
                notifier=notifier,
                issue_url=issue_url,
                dashboard_url=dashboard_url,
            )
            if config is not None and _is_git_repo(config.homelab_repo_path):
                remove_worktree_if_exists(config, _run_id_from_identifier(issue_identifier))


async def reconcile_startup(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
) -> int:
    """Reconcile startup state: clean orphaned worktrees, stale tmux sessions,
    and Plane issues stuck in Running.

    Returns the number of items cleaned up. Runs before the main tick loop so
    the scheduler starts clean after a restart.
    """
    cleaned = 0
    if not _is_git_repo(config.homelab_repo_path):
        LOGGER.debug("reconcile_startup_skipped not_a_git_repo")
        return cleaned

    # Build the set of run_ids that have a live Plane issue in Running state
    # with a non-stale claim comment. Only these are considered "live".
    live_run_ids: set[str] = set()
    stale_running_issues: list[dict[str, Any]] = []
    for issue in await adapter.list_issues_by_state(
        TrackerRole.STATE_RUNNING,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    ):
        issue_id = str(issue["id"])
        identifier = str(issue.get("sequence_id") or issue.get("identifier") or issue_id)
        run_id = _run_id_from_identifier(identifier)
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is not None and (now() - claim_time) <= timedelta(milliseconds=config.run_timeout_ms):
            live_run_ids.add(run_id)
        else:
            stale_running_issues.append({
                "id": issue_id,
                "identifier": identifier,
                "name": issue.get("name", ""),
                "run_id": run_id,
                "claim_time": claim_time,
            })

    # Reap stale Running issues first (transition to Blocked, then clean worktree).
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
        remove_worktree_if_exists(config, issue["run_id"])
        kill_tmux_session(issue["run_id"])
        cleaned += 1
        LOGGER.info(
            "reconcile_startup_reaped_issue issue_id=%s run_id=%s",
            issue["id"], issue["run_id"],
        )

    # Reap orphaned worktrees: worktrees whose run_id has no live Plane issue.
    for wt_path, branch in list_worktrees(config.homelab_repo_path):
        run_id = _run_id_from_worktree_path(config.homelab_repo_path, wt_path)
        if run_id is None:
            continue
        if run_id in live_run_ids:
            continue
        # Not live: this worktree is an orphan. Remove it.
        try:
            remove_worktree(config, run_id)
            LOGGER.info(
                "reconcile_startup_reaped_worktree run_id=%s path=%s branch=%s",
                run_id, wt_path, branch,
            )
        except Exception as exc:
            LOGGER.warning(
                "reconcile_startup_worktree_remove_failed run_id=%s path=%s error=%s",
                run_id, wt_path, exc,
            )
        kill_tmux_session(run_id)
        cleaned += 1

    # Reap orphaned tmux sessions: sessions whose run_id has no live Plane issue
    # and no worktree. Sessions that still have a worktree are handled above.
    # Also skip sessions with live attached clients (handled by kill_tmux_session).
    for worktree_wt_path, _ in list_worktrees(config.homelab_repo_path):
        existing_run_id = _run_id_from_worktree_path(config.homelab_repo_path, worktree_wt_path)
        if existing_run_id is not None:
            live_run_ids.discard(existing_run_id)
    for run_id in live_run_ids:
        kill_tmux_session(run_id)

    LOGGER.info("reconcile_startup_completed cleaned=%d", cleaned)
    return cleaned


def init_run_semaphore(config: SymphonyConfig) -> None:
    """Create or replace the global live-run semaphore with the configured cap.

    Called once at startup and when the cap changes. Must be called before
    run_loop uses the semaphore.
    """
    global _RUN_SEMAPHORE, _POLL_INTERVAL_S, _IN_FLIGHT_ISSUE_IDS, _IN_FLIGHT_LOCK
    _RUN_SEMAPHORE = asyncio.Semaphore(config.run_cap)
    _POLL_INTERVAL_S = config.poll_interval_ms / 1000
    _IN_FLIGHT_ISSUE_IDS = set()
    _IN_FLIGHT_LOCK = asyncio.Lock()


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
    Each task holds its semaphore slot until the Run's worktree cleanup completes
    (on all exit paths — verdict, crash, timeout).
    Per-tick single-run serialization is removed; the semaphore cap is the only
    concurrency governor.
    """
    next_blocked_reconcile_at = datetime.now(UTC)
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
        if slots_available > 0:
            task = asyncio.create_task(
                _dispatch_one(config, adapter, agent_runner, render_prompt, notifier, run_blocked_reconcile, state)
            )
            active_tasks.add(task)

        if active_tasks:
            done_wait, pending = await asyncio.wait(
                active_tasks,
                timeout=state.poll_interval,
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
                await asyncio.sleep(state.poll_interval)
        else:
            await asyncio.sleep(state.poll_interval)


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
        available = [
            candidate
            for candidate in candidates
            if candidate.id not in ids
        ]
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
            or not _labels_contain_role(issue.labels, contract, TrackerRole.APPROVAL_REQUIRED)
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
            return _ScheduledSelection(candidate, "scheduled-malformed", error="not_before missing")
        if event.not_before > now_dt:
            continue
        due.append((event.not_before, candidate.created_at, candidate.id, candidate, event))
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
    if SCHEDULED_LABEL_WINDOW_START_HOUR <= local_now.hour < SCHEDULED_LABEL_WINDOW_END_HOUR:
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


def _response_items(response: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _candidate_from_issue(issue: dict[str, Any], *, labels: tuple[str, ...]) -> CandidateIssue:
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


async def _latest_schedule_event(adapter: TrackerAdapter, issue_id: str) -> ScheduleEvent | None:
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
        CommentPayload(body=f"Symphony schedule cancellation repaired stale scheduled label: {reason}"),
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
                issue_name, issue_identifier, reason,
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
                    issue_name, issue_identifier, message,
                    issue_url=issue_url,
                    dashboard_url=dashboard_url,
                )
            )
        except Exception as exc:
            LOGGER.warning("notification_error issue_id=%s error=%s", issue_id, exc)


def _is_state(issue: dict[str, Any], adapter: TrackerAdapter, state: TrackerRole) -> bool:
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


def _repo_dirty(repo_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        LOGGER.warning("git_status_error repo=%s error=%s", repo_path, exc)
        return True
    if result.returncode != 0:
        LOGGER.warning(
            "git_status_failed repo=%s returncode=%s stderr=%s",
            repo_path, result.returncode, result.stderr.strip(),
        )
        return True
    return bool(result.stdout.strip())


def _diff_stat(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "No diff stat available"


# Symphony bot identity used for auto-commits when an agent leaves the
# homelab worktree dirty. See _auto_commit below.
_SYMPHONY_GIT_NAME = "Symphony"
_SYMPHONY_GIT_EMAIL = "symphony@testytech.net"


class AutoCommitFailed(RuntimeError):
    """Raised when the scheduler cannot auto-commit dirty changes."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def _auto_commit(
    repo_path: Path,
    *,
    issue_identifier: str,
    issue_name: str,
    issue_id: str,
    plan_path: str | None = None,
) -> str:
    """Stage and commit dirty changes under the Symphony bot identity.

    Returns the resulting commit SHA. Raises AutoCommitFailed if any git
    invocation fails. No push is performed.
    """

    git_env = ["-c", f"user.name={_SYMPHONY_GIT_NAME}",
               "-c", f"user.email={_SYMPHONY_GIT_EMAIL}"]

    status = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise AutoCommitFailed(
            f"git status failed (exit {status.returncode})",
            stderr=status.stderr.strip(),
        )

    paths = _dirty_paths_from_porcelain_z(status.stdout)
    if not paths:
        raise AutoCommitFailed("git commit failed (exit 1)", stderr="nothing to commit")

    if plan_path:
        allowed_plan_paths = _allowed_plan_artifact_paths(repo_path, Path(plan_path))
        for path in paths:
            if path.startswith("plans/") and path not in allowed_plan_paths:
                raise AutoCommitFailed(
                    f"refusing to auto-commit unrelated plan artifact: {path}"
                )

    add = subprocess.run(
        ["git", *git_env, "add", "--", *paths],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if add.returncode != 0:
        raise AutoCommitFailed(
            f"git add failed (exit {add.returncode})",
            stderr=add.stderr.strip(),
        )

    title = f"Symphony: {issue_identifier} {issue_name}".strip()
    trailer = f"Plane-Issue: {issue_id}"
    message_args = ["-m", title, "-m", trailer]
    if plan_path:
        message_args.extend(["-m", f"Plan-Path: {plan_path}"])
    commit = subprocess.run(
        ["git", *git_env, "commit", *message_args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise AutoCommitFailed(
            f"git commit failed (exit {commit.returncode})",
            stderr=commit.stderr.strip() or commit.stdout.strip(),
        )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if sha.returncode != 0:
        raise AutoCommitFailed(
            f"git rev-parse HEAD failed (exit {sha.returncode})",
            stderr=sha.stderr.strip(),
        )
    return sha.stdout.strip()


def _dirty_paths_from_porcelain_z(output: str) -> list[str]:
    entries = output.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index < len(entries) and entries[index]:
                path = entries[index]
                index += 1
        if path:
            paths.append(path)
    return paths


def _allowed_plan_artifact_paths(repo_path: Path, plan_path: Path) -> set[str]:
    resolved_plan = plan_path.resolve()
    resolved_state = _state_path_for_plan(resolved_plan).resolve()
    allowed: set[str] = set()
    for path in (resolved_plan, resolved_state):
        try:
            allowed.add(path.relative_to(repo_path.resolve()).as_posix())
        except ValueError:
            continue
    return allowed
