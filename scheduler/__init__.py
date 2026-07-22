"""Core Symphony scheduler loop."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from agent_runner import AgentAdapter, AgentResult
from blocked_reconciler import reconcile_blocked  # noqa: F401  (re-export: scheduler.reconcile_blocked is the public monkeypatch surface)
from claude_runner import claude_probe_failure_reason, sweep_persistent_claude_sessions
from code_version import resolve_code_sha
from config import ProjectBinding, SymphonyConfig
from model_catalog import load_models, resolve_model
from notifier import (
    TelegramNotifier,
    format_blocked_message,
    format_review_message,
)
from plane_adapter import PlaneRateLimitError
from prompt_renderer import render_previous_comments_block, review_mode
from redispatch_core import (
    COMMIT_REDISPATCH_REPLY_PREFIX,
    MAX_COMMIT_REDISPATCH,
    OPERATOR_RELAND_PENDING_PREFIX,
    RELAND_PENDING_PREFIX,
    count_commit_redispatches,
    operator_reland_done_body,
    operator_reland_unconsumed,
)
from .reland import (
    _commit_redispatch_body as _commit_redispatch_body,
    _commit_redispatch_body_base as _commit_redispatch_body_base,
    _land_review_worktree as _land_review_worktree,
    _next_review_dispatch_marker as _next_review_dispatch_marker,
    _reland_done_body as _reland_done_body,
    _reland_done_count as _reland_done_count,
    _reland_pending_count as _reland_pending_count,
    _review_base_repo_branch as _review_base_repo_branch,
    _review_base_repo_dirty as _review_base_repo_dirty,
    _review_worktree_diff_empty as _review_worktree_diff_empty,
    _review_worktree_is_dirty as _review_worktree_is_dirty,
)
from repo_host import repo_host_for
from schedule import (
    SCHEDULED_LABEL_WINDOW_END_HOUR as _SCHEDULED_LABEL_WINDOW_END_HOUR,
)
from schedule import (
    SCHEDULED_LABEL_WINDOW_START_HOUR as _SCHEDULED_LABEL_WINDOW_START_HOUR,
)
from schedule import (
    SCHEDULED_LABEL_WINDOW_TZ as _SCHEDULED_LABEL_WINDOW_TZ,
)
from schedule import (
    ScheduleEvent,
    format_schedule_comment,
)
from session_continuity import (
    ACTION_RESUME,
    REASON_SESSION_ABSENT,
    ResumeDecision,
    derive_session_id,
    evaluate_resume_eligibility,
)
from tracker_adapter import TrackerAdapter
from tracker_contract import DEFAULT_CONTRACT, TrackerContract, TrackerRole
from tracker_types import (
    CandidateIssue,
    CommentPayload,
    _extract_labels,  # noqa: F401  (re-export: scheduler._extract_labels is the public test surface)
    _is_state,
    _parse_iso,
)
from .bindings import (
    binding_for_issue as _binding_for_issue,
    worktree_enabled as _worktree_enabled,
    worktree_run_fields as _worktree_run_fields,
)
from .dispatch_state import (  # noqa: F401  (SchedulerError + rate-limit/cooldown re-exports: scheduler._NAME is the public test/patch surface)
    SchedulerError,
    _cooldown_remaining_s,
    _DispatchState,
    _effective_run_cap,
    _new_dispatch_state,
    _record_rate_limit,
)
from .markers import (
    _SCHEDULE_MARKER_RE as _SCHEDULE_MARKER_RE,
)
from .markers import (
    _bound_summary_block as _bound_summary_block,
)
from .markers import (
    _hit_approval_gate as _hit_approval_gate,
)
from .markers import (
    _hit_permission_gate as _hit_permission_gate,
)
from .markers import (
    _parse_question_block as _parse_question_block,
)
from .markers import (
    _parse_result_marker as _parse_result_marker,
)
from .markers import (
    _parse_run_metrics as _parse_run_metrics,
)
from .markers import (
    _parse_schedule_marker as _parse_schedule_marker,
)
from .markers import (
    _parse_summary_block as _parse_summary_block,
)
from .markers import (
    _parse_summary_marker as _parse_summary_marker,
)
from .ports import (
    fetch_issue as _fetch_issue,
)
from .ports import (
    maybe_await as _maybe_await,
)
from .run_records import (
    finish_run_record as _finish_run_record,
    handle_archived_terminal as _handle_archived_terminal,
    mark_run_record_running as _mark_run_record_running,
    start_run_record as _start_run_record,
)
from .sanitize import (
    _capture_natural_turn as _capture_natural_turn,
)
from .sanitize import (
    _collect_secrets as _collect_secrets,
)
from .sanitize import (
    _extract_question as _extract_question,
)
from .sanitize import (
    _extract_summary as _extract_summary,
)
from .sanitize import (
    _format_previous_comment_body as _format_previous_comment_body,
)
from .sanitize import (
    _format_report as _format_report,
)
from .sanitize import (
    _format_stderr_summary as _format_stderr_summary,
)
from .sanitize import (
    _sanitize_report as _sanitize_report,
)
from .stamp import _stamp_comment  # noqa: F401
from .selection import (  # noqa: F401  (_reserve/_release re-exports: scheduler._NAME is the public test surface)
    _release_candidate,
    _reserve_candidate,
    _reserve_specific_candidate,
    labels_contain_role as _labels_contain_role,
)
from .transient_retry import (
    MAX_COMBINED_RETRIES,
    MAX_OVERLOAD_RETRIES,
    MAX_STALL_RETRIES,
    MAX_TIMEOUT_RETRIES,
    PI_RETRY_TAGS,
    STALL_WATCHDOG_SENTINEL,
    count_all_retries,
    count_retries,
    count_stall_retries,
    format_retry_marker,
    format_stall_retry_marker,
    is_transient,
    retry_cooldown_expired,
)

_wake_signal = import_module("web.api.wake_signal")
consume_wake_sentinel = _wake_signal.consume_wake_sentinel


LOGGER = logging.getLogger(__name__)
# Legacy claim-time fallback: kept so ``_claimed_at`` can still parse claim
# timestamps from comments on adapters without a Run store (Plane) and from
# historical issues. New claim time comes from the Run record's ``started_at``.
CLAIM_PREFIX = "Symphony claimed at "
REPORT_MAX_BYTES = 2048
# Matches CSI escape sequences (e.g. \x1b[0m, \x1b[90m, \x1b[1;31m). Stripped
# from agent stderr so failure comments are readable on Plane, which renders
# fenced code as plain text.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
SCHEDULED_RELEASE_PAGE_SIZE = 50
SCHEDULED_RELEASE_MAX_PAGES_PER_TICK = 3
REVIEW_LAND_RETRY_DELAY_S = 2.0
LOG_RETENTION_INTERVAL = timedelta(hours=24)
WAKE_SENTINEL_CHECK_INTERVAL_S = 1.0

SCHEDULED_LABEL_WINDOW_TZ = _SCHEDULED_LABEL_WINDOW_TZ
SCHEDULED_LABEL_WINDOW_START_HOUR = _SCHEDULED_LABEL_WINDOW_START_HOUR
SCHEDULED_LABEL_WINDOW_END_HOUR = _SCHEDULED_LABEL_WINDOW_END_HOUR
SCHEDULED_LABEL_DEFAULT_REASON = "scheduled label maintenance window"
SCHEDULED_LABEL_DEFAULT_SOURCE = "scheduled label maintenance window (12am-6am PT)"


def _fixed_now(value: datetime) -> Callable[[], datetime]:
    def now() -> datetime:
        return value

    return now


# Cap the blocked-reason text sent to the Telegram notifier, leaving headroom
# under Telegram's 4096-char limit for the name/identifier/URL wrapping.
NOTIFY_REASON_MAX_CHARS = 2000


_SECRET_ENV_KEYS = (
    "PLANE_API_KEY",
    "SYMPHONY_PLANE_API_KEY",
    "ZAI_API_KEY",
    "CLIP" + "ROXY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
)


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
    # Patrol session generation: count // 3 before creation so Runs 1-3 share
    # generation 0, Run 4 starts generation 1, etc.  Non-patrol always gen 0.
    session_generation = 0
    if candidate.fresh_context:
        # A loop Run must never reopen a prior native CLI session. Podium Run
        # ids are monotonic, so the previous Run id gives every dispatch a new
        # derived session id without adding persistence.
        session_generation = int(fresh_issue.get("latest_run_id") or 0)
    elif candidate.origin == "patrol":
        dc = int(fresh_issue.get("patrol_dispatch_count") or 0)
        session_generation = dc // 3
    session_id = derive_session_id(candidate.id, generation=session_generation)
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
        worktree_active=_worktree_enabled(config, candidate, binding=binding),
    )
    if candidate.fresh_context:
        return base_candidate, None

    supports_resume = agent == "claude" or (
        agent == "pi" and getattr(binding, "pi_mode", "one-shot") == "rpc"
    )
    if (
        binding is None
        or not supports_resume
        or (binding.is_remote and agent == "claude")
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
    prompt_candidate = candidate
    if candidate.fresh_context:
        prompt_candidate = replace(candidate, comments_md="", context_md="")
    prompt = _invoke_renderer(
        render_prompt,
        prompt_candidate,
        resume=getattr(candidate, "resumed", False),
    )
    # Podium's renderer already embeds comments_md as the canonical
    # "## Previous Issue Comments" block (with operator-reply flagging), so
    # appending here too would double-inject the whole thread. Only the Plane
    # path (no context store) needs the scheduler to attach comments.
    if (
        comments_text
        and not getattr(candidate, "resumed", False)
        and not candidate.fresh_context
        and not getattr(adapter, "stores_context", False)
    ):
        prompt = f"{prompt}\n\n{render_previous_comments_block(comments_text)}"
    return candidate, prompt


def _extract_runnable_verification(issue_body: str) -> str:
    """Return a shell command from a cleanly-runnable ## Verification section."""
    heading = re.search(r"^##[ \t]+Verification[ \t]*$", issue_body, re.MULTILINE)
    if heading is None:
        return ""
    next_heading = re.search(r"^##[ \t]+", issue_body[heading.end() :], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(issue_body)
    section = issue_body[heading.end() : end]
    parts = section.split("`")
    if len(parts) < 3 or len(parts) % 2 == 0:
        return ""
    commands: list[str] = []
    for index, part in enumerate(parts):
        if index % 2:
            command = part.strip()
            if not command:
                return ""
            commands.append(command)
            continue
        if re.sub(r"\b(?:and|then)\b|[\s,.;:]", "", part, flags=re.IGNORECASE):
            return ""
    return " && ".join(commands)


def _review_verification_cwd(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None,
) -> Path:
    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    if _worktree_enabled(config, candidate, binding=resolved_binding):
        binding_name = candidate.binding_name or (
            resolved_binding.name if resolved_binding is not None else ""
        )
        if binding_name:
            worktree_helpers = import_module("worktree_facade")
            return cast(
                Path,
                worktree_helpers.worktree_dir(
                    config.homelab_repo_path,
                    binding_name,
                    str(candidate.id),
                ),
            )
    return config.homelab_repo_path


def _run_runnable_verification(command: str, cwd: Path) -> int:
    try:
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        LOGGER.warning("review_verification_exec_error cwd=%s error=%s", cwd, exc)
        return 127
    if completed.returncode != 0:
        LOGGER.warning(
            "review_verification_failed cwd=%s returncode=%s stdout=%r stderr=%r",
            cwd,
            completed.returncode,
            completed.stdout[-1000:],
            completed.stderr[-1000:],
        )
    return completed.returncode


def _run_review_verification(
    command: str,
    cwd: Path,
    *,
    binding: ProjectBinding | None,
) -> int:
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(int, remote_worktree.run_verification(binding.remote, cwd, command))
    return _run_runnable_verification(command, cwd)


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
    if (
        agent == "claude"
        and not (binding is not None and binding.is_remote)
        and (probe_failure := claude_probe_failure_reason())
    ):
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
        try:
            source_exists = Path(skill_source).is_file()
        except PermissionError:
            return candidate, (
                f"Dispatch blocked: cannot read skill source for `{skill}` "
                f"(permission denied): {skill_source}"
            )
        if not source_exists:
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


@dataclass(frozen=True)
class _RunTickSelection:
    candidate: CandidateIssue
    scheduled_reserved: bool = False


@dataclass(frozen=True)
class _RunTickGate:
    candidate: CandidateIssue
    mode: str
    fresh_issue: dict[str, Any]


@dataclass(frozen=True)
class _RunTickPreparedDispatch:
    candidate: CandidateIssue
    prompt: str
    comments_text: str
    run_id: str | None
    run_log_path: Path | None
    claim_dt: datetime
    secrets: list[str]
    parse_stderr: bool


@dataclass(frozen=True)
class _RunTickAgentResult:
    candidate: CandidateIssue
    result: AgentResult
    run_id: str | None
    run_log_path: Path | None
    claim_dt: datetime


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


async def _append_terminal_output_context(
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    stdout: str,
    stderr: str,
) -> None:
    if not getattr(adapter, "stores_context", False):
        return
    context_parts = []
    if stdout:
        context_parts.append(f"## Agent stdout\n\n```\n{stdout}\n```")
    if stderr:
        context_parts.append(f"## Agent stderr\n\n```\n{stderr}\n```")
    if context_parts:
        await adapter.append_context(candidate.id, "\n\n".join(context_parts))


async def _maybe_transient_review_retry(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    result: AgentResult,
    *,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    parse_stderr: bool,
    notifier: TelegramNotifier | None,
    now: Callable[[], datetime],
    mode: str,
    comments_md: str | None = None,
    summary: str | None = None,
) -> TickResult | None:
    if not getattr(candidate, "review_dispatch", False):
        return None
    if not is_transient(result.stderr, result.exit_code, result.timed_out):
        return None

    now_dt = now()
    comments_md = (
        comments_md
        if comments_md is not None
        else getattr(candidate, "comments_md", "") or ""
    )
    prior = count_retries(comments_md)
    cap = MAX_TIMEOUT_RETRIES if result.timed_out else MAX_OVERLOAD_RETRIES
    retry_summary = _extract_summary(result, secrets, include_stderr=parse_stderr)
    if prior < cap:
        marker = format_retry_marker(
            prior + 1, "timeout" if result.timed_out else "transient", now_dt
        )
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="failed",
            verdict="retry",
            summary=retry_summary or "Transient review failure; retry queued.",
            ended_at=now_dt.isoformat(),
        )
        await adapter.add_comment(
            candidate.id,
            CommentPayload(
                body=_stamp_comment("system", f"{marker}\n\n{RELAND_PENDING_PREFIX} · {now_dt.isoformat()}")
            ),
        )
        await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
        return TickResult(True, "transient-retry-review", candidate.id, mode=mode)

    if prior >= cap:
        msg = f"Transient review failure retry cap exhausted after {prior} retries."
        if summary:
            msg += f"\n\n{summary}"
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="failed",
            verdict="blocked",
            summary=summary or retry_summary or msg,
            ended_at=now_dt.isoformat(),
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
        return TickResult(
            True, "transient-retry-exhausted-review", candidate.id, mode=mode
        )
    return None


async def _retry_comments_text(
    adapter: TrackerAdapter, candidate: CandidateIssue
) -> str:
    if candidate.comments_md:
        return candidate.comments_md
    issue = await _fetch_issue(adapter, candidate.id)
    if issue.get("comments_md"):
        return str(issue.get("comments_md") or "")
    comments = await adapter.list_comments(candidate.id)
    return "\n\n".join(
        str(comment.get("body") or comment.get("comment_html") or "")
        for comment in comments
    )


async def _fresh_retry_comments_text(
    adapter: TrackerAdapter, candidate: CandidateIssue
) -> str:
    issue = await _fetch_issue(adapter, candidate.id)
    if issue.get("comments_md"):
        return str(issue.get("comments_md") or "")
    comments = await adapter.list_comments(candidate.id)
    return "\n\n".join(
        str(comment.get("body") or comment.get("comment_html") or "")
        for comment in comments
    )


async def _block_retry_ceiling(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    result: AgentResult,
    *,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    parse_stderr: bool,
    notifier: TelegramNotifier | None,
    now: Callable[[], datetime],
    mode: str,
    summary: str | None = None,
) -> TickResult:
    total = count_all_retries(getattr(candidate, "comments_md", "") or "")
    msg = f"Combined retry ceiling exhausted after {total} retries."
    if summary:
        msg += f"\n\n{summary}"
    now_dt = now()
    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=result,
        secrets=secrets,
        state="failed",
        verdict="blocked",
        summary=summary or msg,
        ended_at=now_dt.isoformat(),
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
    return TickResult(True, "combined-ceiling-exhausted", candidate.id, mode=mode)


async def _maybe_retry_stall(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    result: AgentResult,
    *,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    parse_stderr: bool,
    notifier: TelegramNotifier | None,
    now: Callable[[], datetime],
    mode: str,
    comments_md: str,
    summary: str | None = None,
) -> TickResult | None:
    # ADR-0034: broaden beyond the RPC stall sentinel (ADR-0027) to also match
    # any pi-retry extension tag — provider-stream stalls where pi keeps
    # narrating never trip the RPC watchdog, so the tagged-exhaustion stderr is
    # the only signal. Closed allowlist (PI_RETRY_TAGS) keeps genuine
    # crashes/keys/config errors fail-closed to block.
    stderr = result.stderr or ""
    if STALL_WATCHDOG_SENTINEL not in stderr and not any(
        tag in stderr for tag in PI_RETRY_TAGS
    ):
        return None

    now_dt = now()
    prior = count_stall_retries(comments_md)
    if prior >= MAX_STALL_RETRIES:
        msg = f"Stall retry cap exhausted after {prior} retries."
        if summary:
            msg += f"\n\n{summary}"
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="failed",
            verdict="blocked",
            summary=summary or msg,
            ended_at=now_dt.isoformat(),
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
        reason = (
            "stall-retry-exhausted-review"
            if getattr(candidate, "review_dispatch", False)
            else "stall-retry-exhausted-implement"
        )
        return TickResult(True, reason, candidate.id, mode=mode)

    body = format_stall_retry_marker(prior + 1, now_dt)
    if getattr(candidate, "review_dispatch", False):
        body = f"{body}\n\n{RELAND_PENDING_PREFIX} · {now_dt.isoformat()}"
        role = TrackerRole.STATE_IN_REVIEW
        reason = "stall-retry-review"
    else:
        role = TrackerRole.STATE_TODO
        reason = "stall-retry-implement"
    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=result,
        secrets=secrets,
        state="failed",
        verdict="retry",
        summary=_extract_summary(result, secrets, include_stderr=parse_stderr)
        or "Agent stalled; retrying.",
        ended_at=now_dt.isoformat(),
    )
    await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("system", body)))
    await adapter.transition_state(candidate.id, role)
    return TickResult(True, reason, candidate.id, mode=mode)


async def _maybe_retry_transient_implement(
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    result: AgentResult,
    *,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    parse_stderr: bool,
    now: Callable[[], datetime],
    mode: str,
    comments_md: str | None = None,
) -> TickResult | None:
    if getattr(candidate, "review_dispatch", False):
        return None
    if not result.timed_out and result.exit_code == 0:
        return None
    if not is_transient(result.stderr, result.exit_code, result.timed_out):
        return None

    comments_md = (
        comments_md
        if comments_md is not None
        else await _retry_comments_text(adapter, candidate)
    )
    retry_count = count_retries(comments_md)
    retry_cap = MAX_TIMEOUT_RETRIES if result.timed_out else MAX_OVERLOAD_RETRIES
    retry_at = now()
    if retry_count >= retry_cap or not retry_cooldown_expired(comments_md, retry_at):
        return None

    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=result,
        secrets=secrets,
        state="failed",
        verdict="retry",
        summary=_extract_summary(result, secrets, include_stderr=parse_stderr)
        or "Transient agent failure; retrying.",
        ended_at=retry_at.isoformat(),
    )
    await adapter.add_comment(
        candidate.id,
        CommentPayload(
            body=_stamp_comment(
                "system",
                format_retry_marker(
                    retry_count + 1,
                    "timeout" if result.timed_out else "overloaded",
                    retry_at,
                ),
            ),
        ),
    )
    await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
    LOGGER.info(
        "transient_retry_implement issue_id=%s attempt=%s cap=%s",
        candidate.id,
        retry_count + 1,
        retry_cap,
    )
    return TickResult(True, "transient-retry-implement", candidate.id, mode=mode)


async def _emit_blocked_terminal(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    result: AgentResult,
    *,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    notifier: TelegramNotifier | None,
    mode: str,
    msg: str,
    reason: str,
    fallback_summary: str,
    summary: str | None,
    ended_at: str,
) -> TickResult:
    """Shared emit for the 6 blocked-terminal reasons in ``_classify_terminal``.

    Callers pre-build ``msg`` (base + summary + optional stderr), pick a
    ``fallback_summary`` for the run record when ``summary`` is empty, and
    supply ``ended_at`` (most call sites use ``now().isoformat()``; the two
    ``agent-scheduled-malformed`` branches pass a pre-computed ``now_dt``).
    ponytail: extracted from 7 nearly-identical blocks (6 reason strings: timeout,
    nonzero, permission-gate, approval-gate, agent-marker-blocked,
    agent-scheduled-malformed). Tests in tests/test_scheduler.py are the safety net.
    """
    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=result,
        secrets=secrets,
        state="failed",
        verdict="blocked",
        summary=summary or fallback_summary,
        ended_at=ended_at,
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
    return TickResult(True, reason, candidate.id, mode=mode)


async def _classify_terminal(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    result: AgentResult,
    *,
    run_id: str | None,
    run_log_path: Path | None,
    claim_dt: datetime,
    secrets: Sequence[str],
    parse_stderr: bool,
    mode: str,
    scheduling: bool,
    notifier: TelegramNotifier | None,
    dispatch_state: _DispatchState,
    now: Callable[[], datetime],
    binding: ProjectBinding | None,
) -> TickResult:
    """Classify terminal agent output and apply final tracker/run transitions."""

    # Closure-bind the 9 cross-branch args so the 6 blocked-terminal branches
    # only have to pass the 5 site-specific args (msg, reason, fallback_summary,
    # summary, ended_at). ponytail: shrinks each call site from ~17 to ~7 LOC.
    _emit = partial(
        _emit_blocked_terminal,
        config,
        adapter,
        candidate,
        result,
        run_id=run_id,
        run_log_path=run_log_path,
        secrets=secrets,
        notifier=notifier,
        mode=mode,
    )

    # Capture the agent's natural turn once, up front, so every terminal branch
    # — including the retry-exhaustion blocks and the failure branches below —
    # can surface the real prose the agent emitted instead of a terse stub.
    # Falls back to a SYMPHONY_SUMMARY block only when the turn is empty.
    agent = binding.resolve_agent(candidate.labels) if binding is not None else "pi"
    summary = _capture_natural_turn(
        result,
        secrets,
        scheduling=scheduling,
        is_claude=agent == "claude",
        binding_name=binding.name if binding else "",
        homelab_repo_path=str(config.homelab_repo_path),
    )
    if summary is None:
        summary = _extract_summary(result, secrets, include_stderr=parse_stderr)

    if result.timed_out or result.exit_code != 0:
        comments_md = getattr(candidate, "comments_md", "") or ""
        if count_all_retries(comments_md) >= MAX_COMBINED_RETRIES:
            return await _block_retry_ceiling(
                config,
                adapter,
                candidate,
                result,
                run_id=run_id,
                run_log_path=run_log_path,
                secrets=secrets,
                parse_stderr=parse_stderr,
                notifier=notifier,
                now=now,
                mode=mode,
                summary=summary,
            )
        try:
            fresh_comments_md = await _fresh_retry_comments_text(adapter, candidate)
            if fresh_comments_md:
                comments_md = fresh_comments_md
        except Exception as exc:
            LOGGER.warning(
                "retry_comments_fetch_failed issue_id=%s error=%s",
                candidate.id,
                exc,
            )
        if count_all_retries(comments_md) >= MAX_COMBINED_RETRIES:
            return await _block_retry_ceiling(
                config,
                adapter,
                candidate,
                result,
                run_id=run_id,
                run_log_path=run_log_path,
                secrets=secrets,
                parse_stderr=parse_stderr,
                notifier=notifier,
                now=now,
                mode=mode,
                summary=summary,
            )
        stall_retry = await _maybe_retry_stall(
            config,
            adapter,
            candidate,
            result,
            run_id=run_id,
            run_log_path=run_log_path,
            secrets=secrets,
            parse_stderr=parse_stderr,
            notifier=notifier,
            now=now,
            mode=mode,
            comments_md=comments_md,
            summary=summary,
        )
        if stall_retry is not None:
            return stall_retry
        transient_retry = await _maybe_transient_review_retry(
            config,
            adapter,
            candidate,
            result,
            run_id=run_id,
            run_log_path=run_log_path,
            secrets=secrets,
            parse_stderr=parse_stderr,
            notifier=notifier,
            now=now,
            mode=mode,
            comments_md=comments_md,
            summary=summary,
        )
        if transient_retry is not None:
            return transient_retry
        retry = await _maybe_retry_transient_implement(
            adapter,
            candidate,
            result,
            run_id=run_id,
            run_log_path=run_log_path,
            secrets=secrets,
            parse_stderr=parse_stderr,
            now=now,
            mode=mode,
            comments_md=comments_md,
        )
        if retry is not None:
            return retry

    if result.timed_out:
        msg = f"Agent timed out after {result.duration_ms} ms"
        _stdout, stderr = _format_report(result, secrets)
        if summary:
            msg += f"\n\n{summary}"
        if stderr:
            msg += f"\n\n{_format_stderr_summary(stderr)}"
        return await _emit(
            msg=msg,
            reason="timeout",
            fallback_summary="Agent timed out.",
            summary=summary,
            ended_at=now().isoformat(),
        )
    if result.exit_code != 0:
        msg = f"Agent failed with exit code {result.exit_code} after {result.duration_ms} ms"
        _stdout, stderr = _format_report(result, secrets)
        if summary:
            msg += f"\n\n{summary}"
        if stderr:
            msg += f"\n\n{_format_stderr_summary(stderr)}"
        return await _emit(
            msg=msg,
            reason="nonzero",
            fallback_summary=f"Agent failed with exit code {result.exit_code}.",
            summary=summary,
            ended_at=now().isoformat(),
        )

    stdout, stderr = _format_report(result, secrets)
    # Verdict marker and permission/approval gates classify from the raw,
    # untruncated streams. ``_format_report`` tail-truncates to REPORT_MAX_BYTES
    # (2 KB) for human-facing comments, which drops a head SYMPHONY_RESULT marker
    # when the agent emits a >2 KB summary — leaving verdict=None while
    # approval-prose surviving in the tail trips ``_hit_approval_gate`` and blocks
    # a clean run (issues #053/#055/#057, run 120). ``_extract_summary`` already
    # parses raw streams; mirror it here. The truncated ``stdout``/``stderr`` stay
    # in use below for bounded human-facing comments.
    class_stdout = result.stdout
    class_stderr = result.stderr if parse_stderr else ""

    if scheduling:
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

    verdict = _parse_result_marker(class_stdout)
    question = _extract_question(result, secrets, include_stderr=parse_stderr)

    if _hit_permission_gate(class_stdout, class_stderr):
        msg = "Agent could not complete because required tool access was denied."
        if summary:
            msg += f"\n\n{summary}"
        if stderr:
            msg += f"\n\n{_format_stderr_summary(stderr)}"
        return await _emit(
            msg=msg,
            reason="permission-gate",
            fallback_summary=msg,
            summary=summary,
            ended_at=now().isoformat(),
        )

    # Schedule marker: scheduling-capable bindings can emit SYMPHONY_SCHEDULE:
    # to defer an issue into a maintenance window. Permission/tool failures
    # still win; scheduling wins over approval-gate false positives and stray
    # result markers.
    if scheduling:
        now_dt = now()
        schedule_marker = _parse_schedule_marker(class_stdout, now=now_dt)
        if schedule_marker is not None:
            not_before, reason = schedule_marker
            if not_before < now_dt:
                msg = (
                    f"Agent requested schedule but not_before={not_before.isoformat()} "
                    f"is in the past. Cannot schedule into the past."
                )
                if summary:
                    msg += f"\n\n{summary}"
                return await _emit(
                    msg=msg,
                    reason="agent-scheduled-malformed",
                    fallback_summary=msg,
                    summary=summary,
                    ended_at=now_dt.isoformat(),
                )

            schedule_comment = format_schedule_comment(
                not_before=not_before, reason=reason
            )
            schedule_body = (
                f"{schedule_comment}\n\n{summary}" if summary else schedule_comment
            )
            await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("system", schedule_body)))
            await adapter.add_labels(candidate.id, [TrackerRole.SCHEDULED])
            await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
            await _finish_run_record(
                adapter,
                run_id,
                run_log_path,
                result=result,
                secrets=secrets,
                state="succeeded",
                verdict=None,
                summary=summary,
                ended_at=now_dt.isoformat(),
            )
            LOGGER.info(
                "state_scheduled issue_id=%s not_before=%s reason=%s",
                candidate.id,
                not_before.isoformat(),
                reason,
            )
            return TickResult(True, "agent-marker-scheduled", candidate.id, mode=mode)

        # Marker line exists but parse failed — malformed/past/reasonless.
        if _SCHEDULE_MARKER_RE.search(class_stdout):
            msg = (
                "Agent emitted a malformed SYMPHONY_SCHEDULE marker: "
                "could not parse not_before or reason is empty."
            )
            if summary:
                msg += f"\n\n{summary}"
            return await _emit(
                msg=msg,
                reason="agent-scheduled-malformed",
                fallback_summary=msg,
                summary=summary,
                ended_at=now_dt.isoformat(),
            )

    if (
        verdict is None
        and question is None
        and _hit_approval_gate(class_stdout, class_stderr)
    ):
        msg = "Agent could not complete because operator approval is required."
        if summary:
            msg += f"\n\n{summary}"
        if stderr:
            msg += f"\n\n{_format_stderr_summary(stderr)}"
        return await _emit(
            msg=msg,
            reason="approval-gate",
            fallback_summary=msg,
            summary=summary,
            ended_at=now().isoformat(),
        )

    if verdict == "blocked":
        if summary:
            msg = summary
        else:
            msg = "Agent reported a blocked result."
            if stderr:
                msg += f"\n\n{_format_stderr_summary(stderr)}"
        return await _emit(
            msg=msg,
            reason="agent-marker-blocked",
            fallback_summary="Agent reported a blocked result.",
            summary=summary,
            ended_at=now().isoformat(),
        )

    if question:
        # Keep the full captured turn so surrounding prose is not lost (issue
        # 474); it already includes the question with protocol markers stripped.
        # Fall back to the extracted question if no turn was captured.
        question_body = summary or question
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="succeeded",
            verdict="review",
            summary=question,
            ended_at=now().isoformat(),
        )
        try:
            await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("agent", question_body)))
            await _append_terminal_output_context(adapter, candidate, stdout, stderr)
        except PlaneRateLimitError:
            dispatch_state.pending_review_issue_ids.add(candidate.id)
            dispatch_state.pending_completion_bodies[candidate.id] = question_body
            LOGGER.info(
                "pending_review_queued issue_id=%s reason=agent-question-park (post-agent comment/context rate-limited)",
                candidate.id,
            )
            raise
        if await _handle_archived_terminal(
            adapter, config, candidate, run_id, binding=binding
        ):
            return TickResult(True, "archived-terminal", candidate.id, mode=mode)
        try:
            await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
        except PlaneRateLimitError:
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

    if scheduling:
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

    if (
        scheduling
        and verdict == "done"
        and binding is not None
        and binding.auto_close_on_verified
        and candidate.origin == "patrol"
    ):
        # Verified-close (ADR-0020): on an opt-in infra binding, a `done` verdict
        # means the agent re-checked the issue's own condition and confirmed it
        # cleared, so close the issue directly instead of parking it in In Review.
        # `review` and unmarked clean runs still go to In Review below; a failed
        # re-check is the agent's cue to emit `review`/`blocked`, and the patrol's
        # next cycle reopens via record_failure if a `done` was wrong.
        close_body = (
            f"**Symphony closed:**\n\n{summary}"
            if summary
            else "**Symphony closed:** Agent verified the condition is cleared."
        )
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="succeeded",
            verdict="done",
            summary=summary,
            ended_at=now().isoformat(),
        )
        await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("system", close_body)))
        await _append_terminal_output_context(adapter, candidate, stdout, stderr)
        if await _handle_archived_terminal(
            adapter, config, candidate, run_id, binding=binding
        ):
            return TickResult(True, "archived-terminal", candidate.id, mode=mode)
        await adapter.transition_state(candidate.id, TrackerRole.STATE_DONE)
        LOGGER.info(
            "state_transitioned issue_id=%s state=done reason=agent-verified-close",
            candidate.id,
        )
        return TickResult(True, "agent-verified-close", candidate.id, mode=mode)

    if await _handle_operator_reland(
        adapter,
        config,
        candidate,
        result=result,
        run_id=run_id,
        run_log_path=run_log_path,
        secrets=secrets,
        summary=summary or "",
        stdout=stdout,
        stderr=stderr,
        now=now,
        notifier=notifier,
        binding=binding,
    ):
        return TickResult(True, "operator-reland-terminal", candidate.id, mode=mode)

    if verdict == "done" and await _handle_review_terminal_done(
        adapter,
        config,
        candidate,
        result=result,
        run_id=run_id,
        run_log_path=run_log_path,
        secrets=secrets,
        summary=summary or "",
        stdout=stdout,
        stderr=stderr,
        now=now,
        notifier=notifier,
        binding=binding,
    ):
        return TickResult(True, "review-terminal-done", candidate.id, mode=mode)

    reason_code = (
        "agent-marker-review" if verdict in {"review", "done"} else "agent-clean-review"
    )
    completion_body = summary or "(no output)"
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
        await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("agent", completion_body)))
        await _append_terminal_output_context(adapter, candidate, stdout, stderr)
    except PlaneRateLimitError:
        dispatch_state.pending_review_issue_ids.add(candidate.id)
        dispatch_state.pending_completion_bodies[candidate.id] = completion_body
        LOGGER.info(
            "pending_review_queued issue_id=%s reason=%s (post-agent comment/context rate-limited)",
            candidate.id,
            reason_code,
        )
        raise
    if await _handle_archived_terminal(
        adapter, config, candidate, run_id, binding=binding
    ):
        return TickResult(True, "archived-terminal", candidate.id, mode=mode)

    # Issue #10 / ADR-0041: worktree-off spawns (origin=automation AND
    # worktree_active=False) commit their work directly to the shared base
    # checkout. The agent has no per-Issue worktree and no review run is
    # dispatched for them (review_dispatch requires auto_land=True), so the
    # implement terminal is the only chance to land the work. Check the base
    # checkout: clean -> done; dirty -> re-dispatch via the existing
    # commit-redispatch pattern, then block after MAX_COMMIT_REDISPATCH so
    # nothing closes to done with uncommitted work. Loops cannot reach this
    # branch because they force worktree_active=True at fire-time.
    #
    # Gate uses the persisted Issue row's worktree_active (not the candidate's
    # effective value) because _prepare_resume_candidate may have overwritten
    # it with the binding capability — a worktree-on spawn on an infra binding
    # (wt_default=False) ends up with effective worktree_active=False but its
    # persisted flag is still True, so it must NOT take the base-checkout path.
    persisted_worktree_active = bool(
        (await _fetch_issue(adapter, candidate.id)).get("worktree_active") or False
    )
    is_worktree_off_spawn = (
        getattr(candidate, "origin", "") == "automation"
        and not persisted_worktree_active
    )
    if is_worktree_off_spawn:
        resolved_binding = _binding_for_issue(config, candidate, binding=binding)
        binding_name = candidate.binding_name or (
            resolved_binding.name if resolved_binding is not None else ""
        )
        if binding_name and await asyncio.to_thread(
            _review_base_repo_dirty, config, resolved_binding
        ):
            prior_redispatches = count_commit_redispatches(
                str(getattr(candidate, "comments_md", "") or "")
            )
            if prior_redispatches >= MAX_COMMIT_REDISPATCH:
                block_msg = (
                    f"Spawn worktree-off land halted: base checkout still "
                    f"uncommitted after {MAX_COMMIT_REDISPATCH} re-dispatches."
                )
                await _emit(
                    msg=block_msg,
                    reason="spawn-worktree-off-dirty-over-cap",
                    fallback_summary=block_msg,
                    summary=summary,
                    ended_at=now().isoformat(),
                )
                return TickResult(
                    True, "spawn-worktree-off-dirty-over-cap", candidate.id, mode=mode
                )
            await adapter.add_comment(
                candidate.id,
                CommentPayload(
                    body=_stamp_comment("system", _commit_redispatch_body_base(
                        config,
                        binding_name,
                        now=now()),
                    )
                ),
            )
            try:
                await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
            except PlaneRateLimitError:
                dispatch_state.pending_review_issue_ids.add(candidate.id)
                LOGGER.info(
                    "pending_review_queued issue_id=%s reason=spawn-worktree-off-dirty-commit-redispatch",
                    candidate.id,
                )
                raise
            LOGGER.info(
                "state_transitioned issue_id=%s state=todo reason=spawn-worktree-off-dirty-commit-redispatch attempt=%s",
                candidate.id,
                prior_redispatches + 1,
            )
            return TickResult(
                True,
                "spawn-worktree-off-dirty-commit-redispatch",
                candidate.id,
                mode=mode,
            )

        # Clean base checkout: work is already committed to base (the agent
        # finished its task). But before we close to done, verify the base
        # checkout is on the candidate's base branch — a stale branch left
        # behind by a previous worktree-merge land would otherwise let us
        # close with work that landed elsewhere. Falls through to redispatch
        # (then block) if the branch doesn't match; this is the same fail-
        # closed contract the dirty-checkout branch enforces.
        candidate_base_branch = (
            getattr(candidate, "base_branch", "") or config.base_branch
        )
        if candidate_base_branch and not await asyncio.to_thread(
            _review_base_repo_branch,
            config,
            resolved_binding,
            candidate_base_branch,
        ):
            LOGGER.warning(
                "spawn_worktree_off_branch_mismatch issue_id=%s base_branch=%s",
                candidate.id,
                candidate_base_branch,
            )
            prior_redispatches_branch = count_commit_redispatches(
                str(getattr(candidate, "comments_md", "") or "")
            )
            if prior_redispatches_branch >= MAX_COMMIT_REDISPATCH:
                block_msg_branch = (
                    f"Spawn worktree-off land halted: base checkout on wrong "
                    f"branch (expected `{candidate_base_branch}`) after "
                    f"{MAX_COMMIT_REDISPATCH} re-dispatches."
                )
                await _emit(
                    msg=block_msg_branch,
                    reason="spawn-worktree-off-branch-mismatch-over-cap",
                    fallback_summary=block_msg_branch,
                    summary=summary,
                    ended_at=now().isoformat(),
                )
                return TickResult(
                    True,
                    "spawn-worktree-off-branch-mismatch-over-cap",
                    candidate.id,
                    mode=mode,
                )
            await adapter.add_comment(
                candidate.id,
                CommentPayload(
                    body=_stamp_comment(
                        "system",
                        "### Symphony Note (spawn worktree-off branch "
                        f"mismatch · {now().isoformat()})\n\n"
                        f"Base checkout is not on the expected branch "
                        f"`{candidate_base_branch}`. Check out the right "
                        f"branch and commit your work there. The Issue will "
                        f"close to done once the base checkout is clean and "
                        f"on `{candidate_base_branch}`.\n\n"
                        f"{COMMIT_REDISPATCH_REPLY_PREFIX} · "
                        f"{now().isoformat()}",
                    ),
                ),
            )
            try:
                await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
            except PlaneRateLimitError:
                dispatch_state.pending_review_issue_ids.add(candidate.id)
                LOGGER.info(
                    "pending_review_queued issue_id=%s "
                    "reason=spawn-worktree-off-branch-mismatch",
                    candidate.id,
                )
                raise
            LOGGER.info(
                "state_transitioned issue_id=%s state=todo "
                "reason=spawn-worktree-off-branch-mismatch attempt=%s",
                candidate.id,
                prior_redispatches_branch + 1,
            )
            return TickResult(
                True,
                "spawn-worktree-off-branch-mismatch",
                candidate.id,
                mode=mode,
            )

        _iu, _du = _build_urls(config, candidate.id)
        try:
            await adapter.transition_state(candidate.id, TrackerRole.STATE_DONE)
        except PlaneRateLimitError:
            dispatch_state.pending_review_issue_ids.add(candidate.id)
            LOGGER.info(
                "pending_review_queued issue_id=%s reason=spawn-worktree-off-auto-landed",
                candidate.id,
            )
            raise
        LOGGER.info(
            "state_transitioned issue_id=%s state=done reason=spawn-worktree-off-auto-landed",
            candidate.id,
        )
        await _notify_review(
            notifier,
            candidate.name,
            candidate.identifier,
            reason="Spawn worktree-off committed to base; auto-landed",
            issue_url=_iu,
            dashboard_url=_du,
        )
        return TickResult(
            True, "spawn-worktree-off-auto-landed", candidate.id, mode=mode
        )

    try:
        await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
    except PlaneRateLimitError:
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
    state = dispatch_state or _new_dispatch_state(config, binding=binding)
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


def _get_issue_for_claude_reaper(
    adapter: TrackerAdapter, issue_id: str
) -> dict[str, Any] | None:
    try:
        return asyncio.run(adapter.get_issue(issue_id))
    except KeyError:
        return None


async def _sweep_persistent_claude_sessions(
    binding: ProjectBinding,
    adapter: TrackerAdapter,
    *,
    now: datetime,
    idle_ttl_s: int,
    max_live: int,
) -> int:
    return await asyncio.to_thread(
        sweep_persistent_claude_sessions,
        binding.name,
        get_issue=lambda issue_id: _get_issue_for_claude_reaper(adapter, issue_id),
        now=now.timestamp(),
        idle_ttl_s=idle_ttl_s,
        max_live=max_live,
    )


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


async def _handle_review_terminal_done(
    adapter: TrackerAdapter,
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    result: AgentResult,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    summary: str,
    stdout: str,
    stderr: str,
    now: Callable[[], datetime],
    notifier: TelegramNotifier | None,
    binding: ProjectBinding | None = None,
) -> bool:
    # Provenance gate: only a run that was itself dispatched as the review
    # (candidate.review_dispatch, set at selection when the issue was in_review
    # with NO marker) terminates through this path. The `### Symphony Review`
    # marker persists in comments_md forever, so it cannot distinguish a review
    # run from a later implement run on the SAME issue reopened via /reply
    # (in_review -> todo): that reopened run must park in_review, not re-land.
    if not getattr(candidate, "review_dispatch", False):
        return False
    issue = await _fetch_issue(adapter, candidate.id)

    _iu, _du = _build_urls(config, candidate.id)
    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    binding_name = candidate.binding_name or (
        resolved_binding.name if resolved_binding is not None else ""
    )
    issue_id = str(candidate.id)
    issue_body = str(issue.get("description") or candidate.description or "")
    if review_mode(issue_body) == "validation":
        if summary:
            completion_body = f"**Symphony review passed:**\n\n{summary}"
        else:
            completion_body = "**Symphony review passed:** Validation held."
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="succeeded",
            verdict="done",
            summary=summary,
            ended_at=now().isoformat(),
        )
        await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("agent", completion_body)))
        await _append_terminal_output_context(adapter, candidate, stdout, stderr)
        if await _handle_archived_terminal(
            adapter, config, candidate, run_id, binding=binding
        ):
            return True
        await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
        LOGGER.info(
            "state_transitioned issue_id=%s state=in-review reason=review-validation-passed",
            candidate.id,
        )
        return True

    base_branch = candidate.base_branch or config.base_branch
    diff_empty = bool(
        binding_name
        and await asyncio.to_thread(
            _review_worktree_diff_empty,
            config,
            resolved_binding,
            binding_name,
            issue_id,
            base_branch,
        )
    )
    diff_empty_and_clean = bool(
        diff_empty
        and not await asyncio.to_thread(
            _review_worktree_is_dirty,
            config,
            resolved_binding,
            binding_name,
            issue_id,
        )
    )
    if diff_empty_and_clean:
        block_summary = (
            "Review halted: nothing to review — implement run produced no changes."
        )
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="failed",
            verdict="blocked",
            summary=block_summary,
            ended_at=now().isoformat(),
        )
        await _append_terminal_output_context(adapter, candidate, stdout, stderr)
        await _block_issue(
            adapter,
            candidate.id,
            block_summary,
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return True

    verification_command = _extract_runnable_verification(issue_body)
    if verification_command:
        verification_cwd = _review_verification_cwd(
            config, candidate, binding=resolved_binding
        )
        returncode = await asyncio.to_thread(
            _run_review_verification,
            verification_command,
            verification_cwd,
            binding=resolved_binding,
        )
        if returncode != 0:
            backstop_summary = (
                f"Review verification backstop failed: `{verification_command}`"
            )
            await _finish_run_record(
                adapter,
                run_id,
                run_log_path,
                result=result,
                secrets=secrets,
                state="failed",
                verdict="blocked",
                summary=backstop_summary,
                ended_at=now().isoformat(),
            )
            await _append_terminal_output_context(adapter, candidate, stdout, stderr)
            await _block_issue(
                adapter,
                candidate.id,
                f"Review verification backstop failed: `{verification_command}` exited {returncode}.",
                issue_name=candidate.name,
                issue_identifier=candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return True

    if summary:
        completion_body = f"**Symphony review passed:**\n\n{summary}"
    else:
        completion_body = "**Symphony review passed:** Reviewer reported success."
    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=result,
        secrets=secrets,
        state="succeeded",
        verdict="done",
        summary=summary,
        ended_at=now().isoformat(),
    )
    await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("agent", completion_body)))
    await _append_terminal_output_context(adapter, candidate, stdout, stderr)
    if await _handle_archived_terminal(
        adapter, config, candidate, run_id, binding=binding
    ):
        return True

    auto_land = bool(issue.get("auto_land") or False)
    if binding_name and await asyncio.to_thread(
        _review_worktree_is_dirty,
        config,
        resolved_binding,
        binding_name,
        issue_id,
    ):
        prior_redispatches = count_commit_redispatches(
            str(issue.get("comments_md") or "")
        )
        if prior_redispatches >= MAX_COMMIT_REDISPATCH:
            await _block_issue(
                adapter,
                candidate.id,
                f"Review halted: still uncommitted after {MAX_COMMIT_REDISPATCH} "
                "re-dispatches; worktree intact.",
                issue_name=candidate.name,
                issue_identifier=candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return True
        await adapter.add_comment(
            candidate.id,
            CommentPayload(
                body=_stamp_comment("agent", _commit_redispatch_body(
                    config,
                    binding_name,
                    issue_id,
                    auto_land=auto_land,
                    now=now()),
                )
            ),
        )
        await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
        LOGGER.info(
            "state_transitioned issue_id=%s state=todo reason=review-dirty-commit-redispatch attempt=%s",
            candidate.id,
            prior_redispatches + 1,
        )
        return True

    if not auto_land:
        await adapter.transition_state(candidate.id, TrackerRole.STATE_IN_REVIEW)
        LOGGER.info(
            "state_transitioned issue_id=%s state=in-review reason=review-passed-awaiting-operator-merge",
            candidate.id,
        )
        return True

    if not binding_name:
        await _block_issue(
            adapter,
            candidate.id,
            "Review auto-land halted: missing binding name.",
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return True

    error = await asyncio.to_thread(
        _land_review_worktree,
        config,
        resolved_binding,
        binding_name,
        issue_id,
        base_branch,
    )
    if error is not None:
        await asyncio.sleep(REVIEW_LAND_RETRY_DELAY_S)
        error = await asyncio.to_thread(
            _land_review_worktree,
            config,
            resolved_binding,
            binding_name,
            issue_id,
            base_branch,
        )
    if error is not None:
        await _block_issue(
            adapter,
            candidate.id,
            error,
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return True

    reland_issue = await _fetch_issue(adapter, candidate.id)
    reland_done_body = _reland_done_body(
        str(reland_issue.get("comments_md") or ""), now=now()
    )
    if reland_done_body:
        await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("system", reland_done_body)))

    update_columns = getattr(adapter, "_update_issue_columns", None)
    if callable(update_columns):
        await _maybe_await(update_columns(candidate.id, {"worktree_active": False}))
    await adapter.transition_state(candidate.id, TrackerRole.STATE_DONE)
    LOGGER.info(
        "state_transitioned issue_id=%s state=done reason=review-auto-landed",
        candidate.id,
    )
    await _notify_review(
        notifier,
        candidate.name,
        candidate.identifier,
        reason="Review passed; worktree auto-landed",
        issue_url=_iu,
        dashboard_url=_du,
    )
    return True


async def _handle_operator_reland(
    adapter: TrackerAdapter,
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    result: AgentResult,
    run_id: str | None,
    run_log_path: Path | None,
    secrets: Sequence[str],
    summary: str,
    stdout: str,
    stderr: str,
    now: Callable[[], datetime],
    notifier: TelegramNotifier | None,
    binding: ProjectBinding | None = None,
) -> bool:
    """Handle operator move-to-done reland after a commit-redispatch run completes.

    Returns True when the operator marker was outstanding AND the function
    handled the issue (landed / re-dispatched / blocked). Returns False when
    no operator marker is outstanding so the generic terminal path should take
    over.
    """
    # Gate: fetch comments_md (candidate attribute or via adapter)
    comments_md = getattr(candidate, "comments_md", "")
    if not comments_md:
        issue = await _fetch_issue(adapter, candidate.id)
        comments_md = str(issue.get("comments_md") or "")
    if not operator_reland_unconsumed(comments_md):
        return False

    _iu, _du = _build_urls(config, candidate.id)
    resolved_binding = _binding_for_issue(config, candidate, binding=binding)
    binding_name = candidate.binding_name or (
        resolved_binding.name if resolved_binding is not None else ""
    )
    issue_id = str(candidate.id)

    # ── 6.3: Dirty worktree ───────────────────────────────────────────
    if binding_name and await asyncio.to_thread(
        _review_worktree_is_dirty,
        config,
        resolved_binding,
        binding_name,
        issue_id,
    ):
        prior = count_commit_redispatches(comments_md)
        if prior >= MAX_COMMIT_REDISPATCH:
            block_msg = (
                f"Operator land halted: still uncommitted after "
                f"{MAX_COMMIT_REDISPATCH} re-dispatches; worktree intact."
            )
            await _finish_run_record(
                adapter,
                run_id,
                run_log_path,
                result=result,
                secrets=secrets,
                state="failed",
                verdict="blocked",
                summary=block_msg,
                ended_at=now().isoformat(),
            )
            await _append_terminal_output_context(adapter, candidate, stdout, stderr)
            await _block_issue(
                adapter,
                candidate.id,
                block_msg,
                issue_name=candidate.name,
                issue_identifier=candidate.identifier,
                notifier=notifier,
                issue_url=_iu,
                dashboard_url=_du,
            )
            return True

        # Under cap: commit-redispatch note + fresh operator pending marker
        commit_body = _commit_redispatch_body(
            config,
            binding_name,
            issue_id,
            auto_land=False,
            now=now(),
        )
        operator_marker = f"\n\n{OPERATOR_RELAND_PENDING_PREFIX} · {now().isoformat()}"
        body = commit_body + operator_marker
        await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("agent", body)))
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="succeeded",
            verdict=None,
            summary=summary,
            ended_at=now().isoformat(),
        )
        await _append_terminal_output_context(adapter, candidate, stdout, stderr)
        await adapter.transition_state(candidate.id, TrackerRole.STATE_TODO)
        LOGGER.info(
            "state_transitioned issue_id=%s state=todo "
            "reason=operator-reland-dirty-commit-redispatch attempt=%s",
            candidate.id,
            prior + 1,
        )
        return True

    # ── 6.4: Land ────────────────────────────────────────────────────
    base_branch = candidate.base_branch or config.base_branch
    error = await asyncio.to_thread(
        _land_review_worktree,
        config,
        resolved_binding,
        binding_name,
        issue_id,
        base_branch,
    )
    if error is not None:
        await asyncio.sleep(REVIEW_LAND_RETRY_DELAY_S)
        error = await asyncio.to_thread(
            _land_review_worktree,
            config,
            resolved_binding,
            binding_name,
            issue_id,
            base_branch,
        )
    if error is not None:
        await _finish_run_record(
            adapter,
            run_id,
            run_log_path,
            result=result,
            secrets=secrets,
            state="failed",
            verdict="blocked",
            summary=error,
            ended_at=now().isoformat(),
        )
        await _append_terminal_output_context(adapter, candidate, stdout, stderr)
        await _block_issue(
            adapter,
            candidate.id,
            error,
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return True

    # Land success: balance operator marker, clear worktree_active, done
    reland_issue = await _fetch_issue(adapter, candidate.id)
    done_body = operator_reland_done_body(
        str(reland_issue.get("comments_md") or ""), now=now()
    )
    if done_body:
        await adapter.add_comment(candidate.id, CommentPayload(body=_stamp_comment("system", done_body)))

    update_columns = getattr(adapter, "_update_issue_columns", None)
    if callable(update_columns):
        await _maybe_await(update_columns(candidate.id, {"worktree_active": False}))
    await _finish_run_record(
        adapter,
        run_id,
        run_log_path,
        result=result,
        secrets=secrets,
        state="succeeded",
        verdict="done",
        summary=summary,
        ended_at=now().isoformat(),
    )
    await _append_terminal_output_context(adapter, candidate, stdout, stderr)
    await adapter.transition_state(candidate.id, TrackerRole.STATE_DONE)
    LOGGER.info(
        "state_transitioned issue_id=%s state=done reason=operator-reland-landed",
        candidate.id,
    )
    return True


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
    await adapter.add_comment(issue_id, CommentPayload(body=_stamp_comment("agent", message)))
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


# Re-exported tick orchestration (moved to .tick module for seam isolation).
from .tick import (  # noqa: E402
    _dispatch_run_tick_agent as _dispatch_run_tick_agent,
    _gate_run_tick_candidate as _gate_run_tick_candidate,
    _prepare_run_tick_dispatch as _prepare_run_tick_dispatch,
    _select_run_tick_candidate as _select_run_tick_candidate,
    run_tick as run_tick,
)

# Re-exported loop lifecycle (moved to .loop module for seam isolation).
from .loop import (  # noqa: E402
    _sleep_or_wake as _sleep_or_wake,
    _wait_for_tasks_or_wake as _wait_for_tasks_or_wake,
    run_loop as run_loop,
)

# Re-exported schedule helpers (moved to .schedule module for seam isolation).
from .schedule import (  # noqa: E402
    _default_scheduled_label_event as _default_scheduled_label_event,
    _detect_agent_schedule as _detect_agent_schedule,
    _latest_schedule_event as _latest_schedule_event,
    _release_scheduled_candidate as _release_scheduled_candidate,
    _repair_cancelled_schedule as _repair_cancelled_schedule,
    _select_scheduled_candidate as _select_scheduled_candidate,
    _with_schedule_context as _with_schedule_context,
)

# Re-exported reconcile functions (moved to .reconcile module for seam isolation).
from .reconcile import (  # noqa: E402,F401  (re-exports: scheduler._NAME is the public test/patch surface)
    fire_spawn_automations as _fire_spawn_automations,
    reconcile_loop_automations as _reconcile_loop_automations,
    reconcile_pending_review as _reconcile_pending_review,
    reconcile_stale_running as _reconcile_stale_running,
    reconcile_startup as _reconcile_startup,
    patrol_run_retention as _run_patrol_run_retention,
    run_log_retention as _run_log_retention,
)
