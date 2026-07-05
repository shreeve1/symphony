"""Scheduler run-records concern module.

Tracker-port run-record lifecycle: mark a Run running, move a returned Run out
of its steerable state, and finalize it (write the on-disk run log, redact, and
persist state/verdict/metrics). All talk through the ``TrackerAdapter`` port
via ``getattr`` sniff + ``maybe_await`` — pure leaves over the adapter, no
dispatch state, no callback into ``scheduler.__init__``.

The two remaining run-records functions — ``_start_run_record`` and
``_handle_archived_terminal`` — are deferred from this slice: they also reach
into binding resolution (``_binding_for_issue``) and worktree helpers
(``_worktree_run_fields`` / remote-worktree cleanup) that do not yet have their
own concern-module homes. Forcing them here would mislocate those helpers.
They land once the binding/worktree seams actualize in later slices.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from agent_runner import AgentResult
from tracker_adapter import TrackerAdapter

from .markers import _parse_run_metrics
from .ports import maybe_await
from .sanitize import _sanitize_report

# The on-disk run log keeps far more than the 2 KB comment/context bound so the
# run-detail pane can show full output; still capped (tail-kept) so a runaway
# agent cannot grow the run-log dir without limit.
LOG_MAX_BYTES = 1_048_576


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
                **_parse_run_metrics(result.stdout),
            },
        )
    )
