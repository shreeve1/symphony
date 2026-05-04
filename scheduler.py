"""Core Symphony scheduler loop."""

from __future__ import annotations

import asyncio
import fcntl
import inspect
import logging
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Protocol, Sequence

from agent_runner import AgentResult
from config import SymphonyConfig
from plane_poller import CandidateIssue, fetch_todo_issues

from homelab_router.plane_adapter import CommentPayload, PlaneAdapter
from homelab_router.plane_contract import PlaneLabel, PlaneState


LOGGER = logging.getLogger(__name__)
CLAIM_PREFIX = "Symphony claimed at "


class SchedulerError(RuntimeError):
    """Raised for scheduler setup failures."""


class LockHeld(RuntimeError):
    """Raised when another scheduler owns the workspace lock."""


class AgentCallable(Protocol):
    def __call__(self, issue: CandidateIssue, rendered_prompt: str) -> AgentResult: ...


@dataclass(frozen=True)
class TickResult:
    dispatched: bool
    reason: str
    issue_id: str | None = None


@contextmanager
def scheduler_lock(lock_path: Path) -> Iterator[object]:
    """Acquire a nonblocking fcntl lock for one scheduler tick."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockHeld("Symphony scheduler lock is already held") from exc
        yield handle
    finally:
        handle.close()


async def run_tick(
    config: SymphonyConfig,
    adapter: PlaneAdapter,
    *,
    agent_runner: AgentCallable,
    render_prompt: Callable[[CandidateIssue], str],
    lock_path: Path | None = None,
    poller: Callable[[PlaneAdapter], Any] = fetch_todo_issues,
    repo_dirty: Callable[[Path], bool] | None = None,
    diff_stat: Callable[[Path], str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> TickResult:
    """Run one scheduler tick without sleeping forever."""

    repo_dirty = _repo_dirty if repo_dirty is None else repo_dirty
    diff_stat = _diff_stat if diff_stat is None else diff_stat
    lock_file = lock_path or config.lock_path
    try:
        with scheduler_lock(lock_file):
            await reconcile_stale_running(adapter, config.run_timeout_ms, now=now)
            try:
                candidates = await _maybe_await(poller(adapter))
            except Exception as exc:
                LOGGER.warning("plane_poll_failed error=%s", exc)
                return TickResult(False, "plane-unreachable")

            if repo_dirty(config.homelab_repo_path):
                LOGGER.warning("worktree_dirty repo=%s", config.homelab_repo_path)
                return TickResult(False, "dirty-worktree")

            candidate = _oldest_candidate(candidates)
            if candidate is None:
                return TickResult(False, "no-candidates")
            if PlaneLabel.APPROVAL_REQUIRED.value in candidate.labels:
                return TickResult(False, "approval-required", candidate.id)

            fresh = await _fetch_issue(adapter, candidate.id)
            if not _is_state(fresh, adapter, PlaneState.TODO):
                return TickResult(False, "state-changed", candidate.id)
            if PlaneLabel.APPROVAL_REQUIRED.value in _extract_labels(fresh):
                return TickResult(False, "approval-required", candidate.id)

            await adapter.transition_state(candidate.id, PlaneState.RUNNING)
            claim_time = now().isoformat()
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=f"{CLAIM_PREFIX}{claim_time}"),
            )
            LOGGER.info("issue_claimed issue_id=%s claimed_at=%s", candidate.id, claim_time)

            try:
                result = agent_runner(candidate, render_prompt(candidate))
            except Exception as exc:
                await _block_issue(adapter, candidate.id, f"Agent crashed: {exc}")
                return TickResult(True, "agent-crashed", candidate.id)

            LOGGER.info(
                "agent_exited issue_id=%s exit_code=%s duration_ms=%s timed_out=%s",
                candidate.id,
                result.exit_code,
                result.duration_ms,
                str(result.timed_out).lower(),
            )
            if result.timed_out:
                await _block_issue(
                    adapter,
                    candidate.id,
                    f"Agent timed out after {result.duration_ms} ms",
                )
                return TickResult(True, "timeout", candidate.id)
            if result.exit_code != 0:
                await _block_issue(
                    adapter,
                    candidate.id,
                    f"Agent failed with exit code {result.exit_code} after {result.duration_ms} ms",
                )
                return TickResult(True, "nonzero", candidate.id)

            if repo_dirty(config.homelab_repo_path):
                stat = diff_stat(config.homelab_repo_path)
                await adapter.add_comment(
                    candidate.id,
                    CommentPayload(body=f"Symphony produced changes:\n```\n{stat}\n```"),
                )
                await adapter.transition_state(candidate.id, PlaneState.IN_REVIEW)
                LOGGER.info("state_transitioned issue_id=%s state=in-review", candidate.id)
                return TickResult(True, "review", candidate.id)

            return TickResult(True, "agent-managed", candidate.id)
    except LockHeld:
        return TickResult(False, "lock-held")


async def reconcile_stale_running(
    adapter: PlaneAdapter,
    run_timeout_ms: int,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Block Running issues whose durable claim comment is stale."""

    if adapter.transport is None:
        raise SchedulerError("Plane transport not configured")
    response = await adapter.transport.get(adapter._issue_path())
    for issue in response.get("results", []):
        if not _is_state(issue, adapter, PlaneState.RUNNING):
            continue
        issue_id = str(issue["id"])
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is None:
            continue
        if now() - claim_time > timedelta(milliseconds=run_timeout_ms):
            await _block_issue(adapter, issue_id, "Symphony claim timed out after scheduler restart")


async def run_loop(
    config: SymphonyConfig,
    adapter: PlaneAdapter,
    *,
    agent_runner: AgentCallable,
    render_prompt: Callable[[CandidateIssue], str],
) -> None:
    """Run the scheduler forever, sleeping between ticks."""

    while True:
        result = await run_tick(
            config,
            adapter,
            agent_runner=agent_runner,
            render_prompt=render_prompt,
        )
        LOGGER.info(
            "tick_completed dispatched=%s reason=%s issue_id=%s",
            str(result.dispatched).lower(),
            result.reason,
            result.issue_id or "",
        )
        await asyncio.sleep(config.poll_interval_ms / 1000)


def _oldest_candidate(candidates: Sequence[CandidateIssue]) -> CandidateIssue | None:
    eligible = [
        issue
        for issue in candidates
        if PlaneLabel.APPROVAL_REQUIRED.value not in issue.labels
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda issue: issue.created_at)[0]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _fetch_issue(adapter: PlaneAdapter, issue_id: str) -> dict[str, Any]:
    if adapter.transport is None:
        raise SchedulerError("Plane transport not configured")
    return await adapter.transport.get(adapter._issue_path(issue_id))


async def _claimed_at(adapter: PlaneAdapter, issue_id: str) -> datetime | None:
    if adapter.transport is None:
        raise SchedulerError("Plane transport not configured")
    response = await adapter.transport.get(adapter._comment_path(issue_id))
    claim_times: list[datetime] = []
    for comment in response.get("results", []):
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


async def _block_issue(adapter: PlaneAdapter, issue_id: str, message: str) -> None:
    await adapter.add_comment(issue_id, CommentPayload(body=message))
    await adapter.transition_state(issue_id, PlaneState.BLOCKED)
    LOGGER.info("state_transitioned issue_id=%s state=blocked", issue_id)


def _is_state(issue: dict[str, Any], adapter: PlaneAdapter, state: PlaneState) -> bool:
    current = issue.get("state")
    wanted = {state.value, adapter._resolve_state(state)}
    if isinstance(current, str):
        return current in wanted
    if isinstance(current, dict):
        return current.get("name") == state.value or current.get("id") in wanted
    return False


def _extract_labels(issue: dict[str, Any]) -> tuple[str, ...]:
    labels = issue.get("labels") or []
    names: list[str] = []
    for label in labels:
        if isinstance(label, str):
            names.append(label)
        elif isinstance(label, dict):
            name = label.get("name") or label.get("value")
            if isinstance(name, str):
                names.append(name)
    return tuple(names)


def _repo_dirty(repo_path: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
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
