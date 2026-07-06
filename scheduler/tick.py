"""Scheduler tick concern module.

Orchestration core: run_tick and its async pipeline helpers moved from
scheduler/__init__.py.  Functions still in __init__ (e.g. _classify_terminal,
_block_issue) are imported lazily to avoid circular deps — they will be
extracted in later slices.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from agent_runner import AgentResult
from config import ProjectBinding, SymphonyConfig
from notifier import TelegramNotifier
from plane_adapter import PlaneRateLimitError
from tracker_adapter import TrackerAdapter
from tracker_contract import TrackerRole
from tracker_types import CandidateIssue, CommentPayload, _extract_labels, _is_state

from .bindings import binding_from_config as _binding_from_config
from .dispatch_state import (
    _DispatchState,
    _clear_rate_limit,
    _new_dispatch_state,
)
from .ports import fetch_issue as _fetch_issue, maybe_await as _maybe_await
from .reconcile import (
    reconcile_pending_review as _reconcile_pending_review,
    reconcile_stale_running as _reconcile_stale_running,
)
from .reland import _next_review_dispatch_marker as _next_review_dispatch_marker
from .run_records import (
    close_run_record_steering as _close_run_record_steering,
    finish_run_record as _finish_run_record,
    mark_run_record_running as _mark_run_record_running,
    start_run_record as _start_run_record,
)
from .sanitize import _collect_secrets as _collect_secrets
from .schedule import (
    _repair_cancelled_schedule,
    _select_scheduled_candidate,
    _with_schedule_context,
)
from .selection import (
    _release_candidate,
    _reserve_candidate,
    _reserve_specific_candidate,
)
from .transient_retry import count_retries, retry_cooldown_expired

LOGGER = logging.getLogger(__name__)


async def _select_run_tick_candidate(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime],
    notifier: TelegramNotifier | None,
    run_blocked_reconciler: bool,
    dispatch_state: _DispatchState,
    binding: ProjectBinding | None,
    poller: Callable[[TrackerAdapter], Any] | None,
) -> "_RunTickSelection | TickResult":  # noqa: F821
    """Run tick selection/reconcile stage and reserve one candidate."""

    from . import (
        TickResult,
        _RunTickSelection,
        _binding_approval_enabled,
        _block_issue,
        _build_urls,
        _release_scheduled_candidate,
        reconcile_blocked,
    )

    await _reconcile_pending_review(config, adapter, dispatch_state, notifier=notifier)

    try:
        await _reconcile_stale_running(
            adapter,
            config.run_timeout_ms,
            now=now,
            notifier=notifier,
            dispatch_state=dispatch_state,
        )
        if (
            config.blocked_reconciler_enabled
            and (binding is not None and binding.blocked_reconciler)
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
        scheduled = (
            await _select_scheduled_candidate(adapter, now=now)
            if (binding is not None and binding.scheduling)
            else None
        )
    except PlaneRateLimitError:
        raise

    scheduled_reserved = False
    candidate: CandidateIssue | None = None
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
    if binding is not None and binding.scheduling:
        candidates = [
            c for c in candidates if not getattr(c, "review_dispatch", False)
        ]
    now_dt = now()
    candidates = [
        c
        for c in candidates
        if getattr(c, "review_dispatch", False)
        or not c.comments_md
        or count_retries(c.comments_md) == 0
        or retry_cooldown_expired(c.comments_md, now_dt)
    ]

    approval_policy_enabled = _binding_approval_enabled(binding) and (
        binding is not None and binding.scheduling
    )
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
    return _RunTickSelection(candidate, scheduled_reserved=scheduled_reserved)


async def _gate_run_tick_candidate(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None,
    notifier: TelegramNotifier | None,
) -> "_RunTickGate | TickResult":  # noqa: F821
    """Run tick gate stage before rendering or dispatch side effects."""

    from . import (  # noqa: F811
        TickResult,
        _RunTickGate,
        _apply_dispatch_gate,
        _binding_approval_enabled,
        _block_issue,
        _build_urls,
        _resolve_mode,
    )

    approval_policy_enabled = _binding_approval_enabled(binding) and (
        binding is not None and binding.scheduling
    )
    if approval_policy_enabled and adapter.labels_contain_role(
        candidate.labels, TrackerRole.APPROVAL_REQUIRED
    ):
        return TickResult(False, "approval-required", candidate.id)

    mode = _resolve_mode(candidate.labels, adapter.contract)

    if getattr(candidate, "review_dispatch", False) and (
        binding is not None and binding.scheduling
    ):
        return TickResult(False, "state-changed", candidate.id)

    expected_state = (
        TrackerRole.STATE_IN_REVIEW
        if getattr(candidate, "review_dispatch", False)
        else TrackerRole.STATE_TODO
    )
    fresh = await _fetch_issue(adapter, candidate.id)
    if not _is_state(
        fresh,
        adapter.contract.state_name_for_role(expected_state),
        adapter.contract.state_value_for_role(expected_state),
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

    if getattr(adapter, "stores_context", False):
        candidate, gate_error = _apply_dispatch_gate(candidate, binding)
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
            return TickResult(False, "dispatch-gate-blocked", candidate.id, mode=mode)

    return _RunTickGate(candidate, mode, fresh)


async def _prepare_run_tick_dispatch(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    fresh_issue: dict[str, Any],
    mode: str,
    render_prompt: Callable[..., str],
    agent_runner: Callable[..., AgentResult],
    *,
    now: Callable[[], datetime],
    binding: ProjectBinding | None,
    notifier: TelegramNotifier | None,
) -> "_RunTickPreparedDispatch | TickResult":  # noqa: F821
    """Prepare prompt, Run record, and claim transition for dispatch."""

    from . import (  # noqa: F811
        TickResult,
        _RunTickPreparedDispatch,
        _block_issue,
        _build_urls,
        _fetch_issue_comments,
        _prepare_resume_candidate,
        _render_for_dispatch,
    )

    try:
        comments_text = await _fetch_issue_comments(adapter, candidate.id)
        candidate, _resume_decision = await _prepare_resume_candidate(
            adapter,
            config,
            candidate,
            fresh_issue,
            binding=binding,
        )
        candidate, prompt = await _render_for_dispatch(
            config,
            adapter,
            candidate,
            render_prompt,
            agent_runner,
            now=now,
            binding=binding,
            comments_text=comments_text,
        )
        if getattr(candidate, "review_dispatch", False):
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=_next_review_dispatch_marker(comments_text)),
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

    run_id, run_log_path = await _start_run_record(
        adapter, config, candidate, binding=binding
    )
    candidate = replace(candidate, active_run_id=run_id or "")
    consumed_skill = getattr(candidate, "preferred_skill", None)
    if run_id is not None and consumed_skill:
        consume = getattr(adapter, "consume_preferred_skill", None)
        if callable(consume):
            await _maybe_await(consume(candidate.id, consumed_skill))
    update_columns = getattr(adapter, "_update_issue_columns", None)
    if getattr(candidate, "worktree_active", False) and callable(update_columns):
        await _maybe_await(update_columns(candidate.id, {"worktree_active": True}))
    await adapter.transition_state(candidate.id, TrackerRole.STATE_RUNNING)
    claim_time = now().isoformat()
    await _mark_run_record_running(
        adapter,
        run_id,
        run_log_path,
        started_at=claim_time,
    )
    claim_dt = datetime.fromisoformat(claim_time)
    LOGGER.info("issue_claimed issue_id=%s claimed_at=%s", candidate.id, claim_time)

    secrets = _collect_secrets(config)
    dispatch_agent = (
        binding.resolve_agent(candidate.labels) if binding is not None else "pi"
    )
    return _RunTickPreparedDispatch(
        candidate=candidate,
        prompt=prompt,
        comments_text=comments_text,
        run_id=run_id,
        run_log_path=run_log_path,
        claim_dt=claim_dt,
        secrets=secrets,
        parse_stderr=dispatch_agent != "claude",
    )


async def _dispatch_run_tick_agent(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    prompt: str,
    *,
    agent_runner: Callable[..., AgentResult],
    render_prompt: Callable[..., str],
    comments_text: str,
    compaction_agent_runner: Callable[..., AgentResult] | None,
    run_id: str | None,
    run_log_path: Path | None,
    claim_dt: datetime,
    secrets: Sequence[str],
    mode: str,
    now: Callable[[], datetime],
    binding: ProjectBinding | None,
    notifier: TelegramNotifier | None,
) -> "_RunTickAgentResult | TickResult":  # noqa: F821
    """Dispatch the agent and retry once from a fresh prompt on resume failure."""

    from . import (  # noqa: F811
        TickResult,
        _RunTickAgentResult,
        _block_issue,
        _build_urls,
        _dispatch_with_resume_fallback,
    )

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
                binding=binding,
                comments_text=comments_text,
                compaction_agent_runner=compaction_agent_runner,
                run_id=run_id,
                run_log_path=run_log_path,
                failed_result=AgentResult(1, 0, False, stdout="", stderr=str(exc)),
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
            binding=binding,
            comments_text=comments_text,
            compaction_agent_runner=compaction_agent_runner,
            run_id=run_id,
            run_log_path=run_log_path,
            failed_result=result,
            secrets=secrets,
            resume_summary=f"resume_failed: exit code {result.exit_code}; fell_back=true",
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
    return _RunTickAgentResult(candidate, result, run_id, run_log_path, claim_dt)


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
) -> "TickResult":  # noqa: F821
    """Run one scheduler tick without sleeping forever."""

    from . import TickResult, _classify_terminal  # noqa: F811

    tick_binding = binding or _binding_from_config(config)
    dispatch_state = dispatch_state or _new_dispatch_state(config, binding=tick_binding)

    selection = await _select_run_tick_candidate(
        config,
        adapter,
        now=now,
        notifier=notifier,
        run_blocked_reconciler=run_blocked_reconciler,
        dispatch_state=dispatch_state,
        binding=tick_binding,
        poller=poller,
    )
    if isinstance(selection, TickResult):
        return selection

    candidate = selection.candidate
    try:
        gate = await _gate_run_tick_candidate(
            config,
            adapter,
            candidate,
            binding=tick_binding,
            notifier=notifier,
        )
        if isinstance(gate, TickResult):
            return gate

        prepared = await _prepare_run_tick_dispatch(
            config,
            adapter,
            gate.candidate,
            gate.fresh_issue,
            gate.mode,
            render_prompt,
            compaction_agent_runner or agent_runner,
            now=now,
            binding=tick_binding,
            notifier=notifier,
        )
        if isinstance(prepared, TickResult):
            return prepared

        dispatched = await _dispatch_run_tick_agent(
            config,
            adapter,
            prepared.candidate,
            prepared.prompt,
            agent_runner=agent_runner,
            render_prompt=render_prompt,
            comments_text=prepared.comments_text,
            compaction_agent_runner=compaction_agent_runner,
            run_id=prepared.run_id,
            run_log_path=prepared.run_log_path,
            claim_dt=prepared.claim_dt,
            secrets=prepared.secrets,
            mode=gate.mode,
            now=now,
            binding=tick_binding,
            notifier=notifier,
        )
        if isinstance(dispatched, TickResult):
            return dispatched

        await _close_run_record_steering(adapter, dispatched.run_id, dispatched.result)

        return await _classify_terminal(
            config,
            adapter,
            dispatched.candidate,
            dispatched.result,
            run_id=dispatched.run_id,
            run_log_path=dispatched.run_log_path,
            claim_dt=dispatched.claim_dt,
            secrets=prepared.secrets,
            parse_stderr=prepared.parse_stderr,
            mode=gate.mode,
            scheduling=(tick_binding.scheduling if tick_binding is not None else True),
            notifier=notifier,
            dispatch_state=dispatch_state,
            now=now,
            binding=tick_binding,
        )
    finally:
        await _release_candidate(candidate.id, dispatch_state=dispatch_state)
