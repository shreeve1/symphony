"""Scheduler run-records concern module.

All five run-record lifecycle functions: start, mark-running, close-steering,
finish, and handle-archived-terminal. Pure leaves over the ``TrackerAdapter``
port — no dispatch state, no callback into ``scheduler.__init__``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from agent_runner import AgentResult
from config import ProjectBinding, SymphonyConfig
from tracker_adapter import TrackerAdapter
from tracker_types import CandidateIssue
from web.api.db import resolve_run_log_root

from .bindings import binding_for_issue as _binding_for_issue
from .bindings import worktree_run_fields as _worktree_run_fields
from .markers import _parse_run_metrics
from .ports import fetch_issue as _fetch_issue
from .ports import maybe_await
from .sanitize import _sanitize_report

LOGGER = logging.getLogger(__name__)

# The on-disk run log keeps far more than the 2 KB comment/context bound so the
# run-detail pane can show full output; still capped (tail-kept) so a runaway
# agent cannot grow the run-log dir without limit.
LOG_MAX_BYTES = 1_048_576


def _run_metrics(result: AgentResult) -> dict[str, Any]:
    """Token/cost columns for a finished run.

    Prefer pi RPC usage harvested from the event stream (input/output/
    cache-read tokens + computed cost). Fall back to SYMPHONY_* stdout markers
    for non-RPC agents (print-mode pi, Claude) that don't stream usage.
    """
    if result.usage:
        return {key: value for key, value in result.usage.items() if value}
    return _parse_run_metrics(result.stdout)


def write_run_log(log_path: Path, stdout: str, stderr: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"## stdout\n\n{stdout}\n\n## stderr\n\n{stderr}\n",
        encoding="utf-8",
    )


async def mark_run_record_running(
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
    await maybe_await(
        cast(Callable[[str, dict[str, Any]], Any], update_run)(
            run_id,
            {"state": "running", "started_at": started_at, "log_path": str(log_path)},
        )
    )


async def close_run_record_steering(
    adapter: TrackerAdapter,
    run_id: str | None,
    result: AgentResult,
) -> None:
    """Move a returned Run out of the steerable state before finalization."""

    if not run_id:
        return
    update_run = getattr(adapter, "update_run", None)
    if not callable(update_run):
        return
    state = "failed" if result.timed_out or result.exit_code != 0 else "succeeded"
    await maybe_await(
        cast(Callable[[str, dict[str, Any]], Any], update_run)(run_id, {"state": state})
    )


async def start_run_record(
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
    run = await maybe_await(
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


async def handle_archived_terminal(
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

    issue_id = str(candidate.id)
    if resolved_binding is not None and resolved_binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        if await asyncio.to_thread(
            remote_worktree.worktree_exists,
            resolved_binding.remote,
            config.homelab_repo_path,
            binding_name,
            issue_id,
        ):
            await asyncio.to_thread(
                remote_worktree.remove_worktree,
                resolved_binding.remote,
                config.homelab_repo_path,
                binding_name,
                issue_id,
            )
    else:
        worktree_helpers = import_module("worktree_facade")
        remove_worktree = worktree_helpers.remove_worktree
        worktree_exists = worktree_helpers.worktree_exists

        if await asyncio.to_thread(
            worktree_exists, config.homelab_repo_path, binding_name, issue_id
        ):
            await asyncio.to_thread(
                remove_worktree, config.homelab_repo_path, binding_name, issue_id
            )

    update_columns = getattr(adapter, "_update_issue_columns", None)
    if callable(update_columns) and issue.get("worktree_active"):
        await maybe_await(update_columns(candidate.id, {"worktree_active": False}))
    return True


async def finish_run_record(
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
    write_run_log(
        log_path,
        _sanitize_report(result.stdout, secrets, max_bytes=LOG_MAX_BYTES),
        _sanitize_report(result.stderr, secrets, max_bytes=LOG_MAX_BYTES),
    )
    update_run = getattr(adapter, "update_run", None)
    if not callable(update_run):
        return
    await maybe_await(
        cast(Callable[[str, dict[str, Any]], Any], update_run)(
            run_id,
            {
                "state": state,
                "verdict": verdict,
                "summary": summary,
                "exit_code": result.exit_code,
                "ended_at": ended_at,
                "log_path": str(log_path),
                **_run_metrics(result),
            },
        )
    )
