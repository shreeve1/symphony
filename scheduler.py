"""Core Symphony scheduler loop."""

from __future__ import annotations

import asyncio
import fcntl
import inspect
import logging
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Protocol, Sequence

from agent_runner import AgentResult
from config import SymphonyConfig
from notifier import TelegramNotifier, format_blocked_message, format_review_message
from plane_poller import CandidateIssue, fetch_todo_issues

from homelab_router.plane_adapter import CommentPayload, PlaneAdapter
from homelab_router.plane_contract import PlaneLabel, PlaneState
from homelab_router.prompt_renderer import render_previous_comments_block


LOGGER = logging.getLogger(__name__)
CLAIM_PREFIX = "Symphony claimed at "
REPORT_MAX_BYTES = 8192
_REDACTED = "***REDACTED***"
_PLAN_HANDOFF_MARKER = "Symphony completed plan."

# SYMPHONY_RESULT marker: agents may emit `SYMPHONY_RESULT: done|review|blocked`
# on its own line in stdout to declare an explicit verdict. Last occurrence wins,
# case-insensitive. Unknown values fall through to the heuristic.
_RESULT_MARKER_RE = re.compile(
    r"^[ \t]*SYMPHONY_RESULT:[ \t]*(done|review|blocked)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_result_marker(stdout: str) -> str | None:
    """Return the last SYMPHONY_RESULT verdict in stdout, or None."""

    if not stdout:
        return None
    matches = _RESULT_MARKER_RE.findall(stdout)
    if not matches:
        return None
    return matches[-1].lower()


class SchedulerError(RuntimeError):
    """Raised for scheduler setup failures."""


def _sanitize_report(text: str, secrets: Sequence[str]) -> str:
    report = text.strip()
    for secret in secrets:
        if secret:
            report = report.replace(secret, _REDACTED)
    encoded = report.encode("utf-8", errors="replace")
    if len(encoded) > REPORT_MAX_BYTES:
        report = encoded[:REPORT_MAX_BYTES].decode("utf-8", errors="replace")
        report += "\n\n... [output truncated]"
    return report


_SECRET_ENV_KEYS = (
    "PLANE_API_KEY",
    "SYMPHONY_PLANE_API_KEY",
    "CLIPROXY_API_KEY",
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


class LockHeld(RuntimeError):
    """Raised when another scheduler owns the workspace lock."""


class AgentCallable(Protocol):
    def __call__(self, issue: CandidateIssue, rendered_prompt: str) -> AgentResult: ...


@dataclass(frozen=True)
class TickResult:
    dispatched: bool
    reason: str
    issue_id: str | None = None
    mode: str = "execute"


def _resolve_mode(labels: tuple[str, ...]) -> str:
    label_set = set(labels)
    if PlaneLabel.BUILD.value in label_set:
        return "build"
    if PlaneLabel.PLAN.value in label_set:
        return "plan"
    return "execute"


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


def _plan_path_from_comments(repo_path: Path, issue: CandidateIssue, comments: list[str]) -> tuple[Path | None, str | None]:
    for body in comments:
        if _PLAN_HANDOFF_MARKER not in body:
            continue
        final_line = _final_non_empty_line(body)
        if not final_line:
            continue
        try:
            return _validate_issue_plan_path(repo_path, issue, final_line), None
        except ValueError as exc:
            return None, str(exc)
    return None, None


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
    auto_commit: Callable[..., str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
) -> TickResult:
    """Run one scheduler tick without sleeping forever."""

    repo_dirty = _repo_dirty if repo_dirty is None else repo_dirty
    diff_stat = _diff_stat if diff_stat is None else diff_stat
    auto_commit = _auto_commit if auto_commit is None else auto_commit
    lock_file = lock_path or config.lock_path
    try:
        with scheduler_lock(lock_file):
            await reconcile_stale_running(adapter, config.run_timeout_ms, now=now, notifier=notifier)
            try:
                candidates = await _maybe_await(poller(adapter))
            except Exception as exc:
                LOGGER.warning("plane_poll_failed error=%s", exc)
                return TickResult(False, "plane-unreachable")

            candidate = _oldest_candidate(candidates)
            if candidate is None:
                return TickResult(False, "no-candidates")
            if PlaneLabel.APPROVAL_REQUIRED.value in candidate.labels:
                return TickResult(False, "approval-required", candidate.id)

            mode = _resolve_mode(candidate.labels)

            pre_dirty = repo_dirty(config.homelab_repo_path)
            if pre_dirty:
                LOGGER.warning("repo_pre_dirty repo=%s", config.homelab_repo_path)

            fresh = await _fetch_issue(adapter, candidate.id)
            if not _is_state(fresh, adapter, PlaneState.TODO):
                return TickResult(False, "state-changed", candidate.id)
            label_ids = adapter.contract.label_ids if adapter.contract else None
            if PlaneLabel.APPROVAL_REQUIRED.value in _extract_labels(fresh, label_ids=label_ids):
                return TickResult(False, "approval-required", candidate.id)

            fresh_labels = _extract_labels(fresh, label_ids=label_ids)
            plan_path: Path | None = None
            if mode == "build":
                if PlaneLabel.PLAN.value in fresh_labels:
                    try:
                        await adapter.remove_labels(candidate.id, [PlaneLabel.PLAN])
                    except Exception as exc:
                        await adapter.add_comment(
                            candidate.id,
                            CommentPayload(body=f"Build could not start: failed to remove stale `plan` label: {exc}"),
                        )
                        return TickResult(False, "stale-plan-label-remove-failed", candidate.id, mode=mode)

                comment_bodies = await _fetch_issue_comment_bodies(adapter, candidate.id)
                plan_path, plan_path_error = _plan_path_from_comments(
                    config.homelab_repo_path, candidate, comment_bodies
                )
                if plan_path_error:
                    await _block_issue(
                        adapter,
                        candidate.id,
                        f"Build could not start: {plan_path_error}.",
                        issue_name=candidate.name,
                        issue_identifier=candidate.identifier,
                        notifier=notifier,
                    )
                    return TickResult(False, "invalid-plan-path", candidate.id, mode=mode)
                if plan_path is None:
                    plan_path = _validated_fallback_plan_path(config.homelab_repo_path, candidate)
                if plan_path is None:
                    try:
                        await adapter.add_labels(candidate.id, [PlaneLabel.PLAN])
                        await adapter.remove_labels(candidate.id, [PlaneLabel.BUILD])
                        await adapter.add_comment(
                            candidate.id,
                            CommentPayload(
                                body=(
                                    "Build could not start because no readable plan file was found. "
                                    "Returning this issue to Plan mode so Symphony can regenerate and post the plan."
                                )
                            ),
                        )
                        await adapter.transition_state(candidate.id, PlaneState.TODO)
                    except Exception as exc:
                        await _block_issue(
                            adapter,
                            candidate.id,
                            f"Build plan recovery failed after no readable plan was found: {exc}",
                            issue_name=candidate.name,
                            issue_identifier=candidate.identifier,
                            notifier=notifier,
                        )
                        return TickResult(False, "build-plan-recovery-failed", candidate.id, mode=mode)
                    return TickResult(False, "build-plan-missing-returned-to-plan", candidate.id, mode=mode)

            await adapter.transition_state(candidate.id, PlaneState.RUNNING)
            claim_time = now().isoformat()
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=f"{CLAIM_PREFIX}{claim_time}"),
            )
            LOGGER.info("issue_claimed issue_id=%s claimed_at=%s", candidate.id, claim_time)

            secrets = _collect_secrets(config)

            comments_text = await _fetch_issue_comments(adapter, candidate.id)
            prompt = render_prompt(candidate)
            if comments_text:
                prompt = f"{prompt}\n\n{render_previous_comments_block(comments_text)}"

            try:
                result = agent_runner(candidate, prompt)
            except Exception as exc:
                await _block_issue(
                    adapter, candidate.id, f"Agent crashed: {exc}",
                    issue_name=candidate.name, issue_identifier=candidate.identifier,
                    notifier=notifier,
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
                if stdout:
                    msg += f"\n\n**Agent Output:**\n```\n{stdout}\n```"
                if stderr:
                    msg += f"\n\n**Stderr:**\n```\n{stderr}\n```"
                await _block_issue(
                    adapter, candidate.id, msg,
                    issue_name=candidate.name, issue_identifier=candidate.identifier,
                    notifier=notifier,
                )
                return TickResult(True, "timeout", candidate.id, mode=mode)
            if result.exit_code != 0:
                msg = f"Agent failed with exit code {result.exit_code} after {result.duration_ms} ms"
                stdout, stderr = _format_report(result, secrets)
                if stdout:
                    msg += f"\n\n**Agent Output:**\n```\n{stdout}\n```"
                if stderr:
                    msg += f"\n\n**Stderr:**\n```\n{stderr}\n```"
                await _block_issue(
                    adapter, candidate.id, msg,
                    issue_name=candidate.name, issue_identifier=candidate.identifier,
                    notifier=notifier,
                )
                return TickResult(True, "nonzero", candidate.id, mode=mode)

            stdout, stderr = _format_report(result, secrets)

            if mode == "plan":
                plan_report_path = _final_non_empty_line(stdout) if stdout else None
                if plan_report_path and not plan_report_path.startswith("/"):
                    plan_report_path = None

                body = _PLAN_HANDOFF_MARKER
                if stdout:
                    body += f"\n\n**Agent Report:**\n```\n{stdout}\n```"
                if stderr:
                    body += f"\n\n**Stderr:**\n```\n{stderr}\n```"
                if repo_dirty(config.homelab_repo_path):
                    stat = diff_stat(config.homelab_repo_path)
                    body += f"\n\n**WARNING: Plan mode produced repository changes:**\n```\n{stat}\n```"
                    LOGGER.warning(
                        "plan_dirty issue_id=%s repo=%s",
                        candidate.id, config.homelab_repo_path,
                    )
                if plan_report_path:
                    body += f"\n\n{plan_report_path}"
                await adapter.add_comment(
                    candidate.id,
                    CommentPayload(body=body),
                )
                await adapter.add_labels(
                    candidate.id, [PlaneLabel.APPROVAL_REQUIRED]
                )
                await adapter.transition_state(candidate.id, PlaneState.IN_REVIEW)
                LOGGER.info("state_transitioned issue_id=%s state=in-review mode=plan", candidate.id)
                await _notify_review(
                    notifier, candidate.name, candidate.identifier,
                    reason="Plan mode completed, awaiting approval",
                )
                return TickResult(True, "plan", candidate.id, mode=mode)

            committed_sha: str | None = None
            committed_stat: str | None = None
            committed_pre_dirty = pre_dirty
            if repo_dirty(config.homelab_repo_path):
                committed_stat = diff_stat(config.homelab_repo_path)
                try:
                    committed_sha = auto_commit(
                        config.homelab_repo_path,
                        issue_identifier=candidate.identifier,
                        issue_name=candidate.name,
                        issue_id=candidate.id,
                        plan_path=str(plan_path) if plan_path else None,
                    )
                except AutoCommitFailed as exc:
                    LOGGER.warning(
                        "auto_commit_failed issue_id=%s repo=%s error=%s",
                        candidate.id, config.homelab_repo_path, exc,
                    )
                    msg = f"Symphony auto-commit failed: {exc}"
                    if exc.stderr:
                        sanitized = _sanitize_report(exc.stderr, secrets)
                        msg += f"\n\n**git stderr:**\n```\n{sanitized}\n```"
                    if committed_stat and committed_stat != "No diff stat available":
                        msg += f"\n\n**Pending diff stat:**\n```\n{committed_stat}\n```"
                    if stdout:
                        msg += f"\n\n**Agent Output:**\n```\n{stdout}\n```"
                    if stderr:
                        msg += f"\n\n**Stderr:**\n```\n{stderr}\n```"
                    await _block_issue(
                        adapter, candidate.id, msg,
                        issue_name=candidate.name,
                        issue_identifier=candidate.identifier,
                        notifier=notifier,
                    )
                    return TickResult(
                        True, "auto-commit-failed", candidate.id, mode=mode,
                    )
                LOGGER.info(
                    "auto_commit_succeeded issue_id=%s sha=%s pre_dirty=%s",
                    candidate.id, committed_sha,
                    str(committed_pre_dirty).lower(),
                )

            after_agent = await _fetch_issue(adapter, candidate.id)
            if _is_state(after_agent, adapter, PlaneState.DONE):
                return TickResult(True, "agent-done", candidate.id, mode=mode)
            if _is_state(after_agent, adapter, PlaneState.IN_REVIEW):
                return TickResult(True, "agent-review", candidate.id, mode=mode)
            if _is_state(after_agent, adapter, PlaneState.BLOCKED):
                return TickResult(True, "agent-blocked", candidate.id, mode=mode)

            # No repo changes, no in-agent state transition. Resolve the
            # agent's verdict from an explicit SYMPHONY_RESULT marker in
            # stdout, or fall through to a clean-exit Done.
            verdict = _parse_result_marker(stdout)

            def _completion_body() -> str:
                body = "**Symphony completed:**"
                if stdout:
                    body += f"\n\n```\n{stdout}\n```"
                else:
                    body = "Symphony completed (no output)."
                if stderr:
                    body += f"\n\n**Stderr:**\n```\n{stderr}\n```"
                if committed_sha is not None:
                    commit_block = (
                        f"\n\n**Symphony auto-committed changes:** `{committed_sha}`"
                    )
                    if committed_pre_dirty:
                        commit_block += (
                            "\n\n**WARNING: Repository was already dirty before "
                            "dispatch.** Commit may include prior work."
                        )
                    if committed_stat and committed_stat != "No diff stat available":
                        commit_block += f"\n\n```\n{committed_stat}\n```"
                    body += commit_block
                return body

            if verdict == "blocked":
                msg = "Agent reported SYMPHONY_RESULT: blocked."
                if committed_sha is not None:
                    msg += (
                        f"\n\n**Symphony auto-committed changes:** `{committed_sha}`"
                    )
                    if committed_stat and committed_stat != "No diff stat available":
                        msg += f"\n\n```\n{committed_stat}\n```"
                if stdout:
                    msg += f"\n\n**Agent Output:**\n```\n{stdout}\n```"
                if stderr:
                    msg += f"\n\n**Stderr:**\n```\n{stderr}\n```"
                await _block_issue(
                    adapter,
                    candidate.id,
                    msg,
                    issue_name=candidate.name,
                    issue_identifier=candidate.identifier,
                    notifier=notifier,
                )
                return TickResult(True, "agent-marker-blocked", candidate.id, mode=mode)

            if verdict == "review":
                await adapter.add_comment(
                    candidate.id,
                    CommentPayload(body=_completion_body()),
                )
                await adapter.transition_state(candidate.id, PlaneState.IN_REVIEW)
                LOGGER.info(
                    "state_transitioned issue_id=%s state=in-review reason=marker",
                    candidate.id,
                )
                await _notify_review(
                    notifier, candidate.name, candidate.identifier,
                    reason="Agent reported SYMPHONY_RESULT: review",
                )
                return TickResult(True, "agent-marker-review", candidate.id, mode=mode)

            # verdict == "done" or no marker: trust clean exit and mark Done.
            reason_code = "agent-marker-done" if verdict == "done" else "agent-clean-done"
            await adapter.add_comment(
                candidate.id,
                CommentPayload(body=_completion_body()),
            )
            await adapter.transition_state(candidate.id, PlaneState.DONE)
            LOGGER.info(
                "state_transitioned issue_id=%s state=done reason=%s",
                candidate.id, reason_code,
            )
            return TickResult(True, reason_code, candidate.id, mode=mode)
    except LockHeld:
        return TickResult(False, "lock-held")


async def reconcile_stale_running(
    adapter: PlaneAdapter,
    run_timeout_ms: int,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
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
            issue_name = str(issue.get("name", ""))
            issue_identifier = str(issue.get("sequence_id", ""))
            await _block_issue(
                adapter, issue_id, "Symphony claim timed out after scheduler restart",
                issue_name=issue_name, issue_identifier=issue_identifier,
                notifier=notifier,
            )


async def run_loop(
    config: SymphonyConfig,
    adapter: PlaneAdapter,
    *,
    agent_runner: AgentCallable,
    render_prompt: Callable[[CandidateIssue], str],
    notifier: TelegramNotifier | None = None,
) -> None:
    """Run the scheduler forever, sleeping between ticks."""

    while True:
        result = await run_tick(
            config,
            adapter,
            agent_runner=agent_runner,
            render_prompt=render_prompt,
            notifier=notifier,
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


async def _fetch_issue_comments(adapter: PlaneAdapter, issue_id: str) -> str:
    if adapter.transport is None:
        return ""
    response = await adapter.transport.get(adapter._comment_path(issue_id))
    comments = response.get("results", [])
    comments.sort(key=lambda c: c.get("created_at", ""))
    parts: list[str] = []
    for comment in comments:
        body = str(comment.get("body") or comment.get("comment_html") or "").strip()
        if CLAIM_PREFIX in body or not body:
            continue
        created = comment.get("created_at", "")
        parts.append(f"**Comment ({created}):**\n{body}")
    return "\n\n---\n\n".join(parts)


async def _fetch_issue_comment_bodies(
    adapter: PlaneAdapter,
    issue_id: str,
    *,
    newest_first: bool = True,
) -> list[str]:
    if adapter.transport is None:
        return []
    response = await adapter.transport.get(adapter._comment_path(issue_id))
    comments = response.get("results", [])
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


async def _notify_review(
    notifier: TelegramNotifier | None,
    issue_name: str,
    issue_identifier: str,
    reason: str = "",
) -> None:
    if notifier is None:
        return
    try:
        await notifier.send(format_review_message(issue_name, issue_identifier, reason))
    except Exception as exc:
        LOGGER.warning("notification_error error=%s", exc)


async def _block_issue(
    adapter: PlaneAdapter,
    issue_id: str,
    message: str,
    *,
    issue_name: str = "",
    issue_identifier: str = "",
    notifier: TelegramNotifier | None = None,
) -> None:
    await adapter.add_comment(issue_id, CommentPayload(body=message))
    await adapter.transition_state(issue_id, PlaneState.BLOCKED)
    LOGGER.info("state_transitioned issue_id=%s state=blocked", issue_id)
    if notifier:
        try:
            await notifier.send(
                format_blocked_message(issue_name, issue_identifier, message)
            )
        except Exception as exc:
            LOGGER.warning("notification_error issue_id=%s error=%s", issue_id, exc)


def _is_state(issue: dict[str, Any], adapter: PlaneAdapter, state: PlaneState) -> bool:
    current = issue.get("state")
    wanted = {state.value, adapter._resolve_state(state)}
    if isinstance(current, str):
        return current in wanted
    if isinstance(current, dict):
        return current.get("name") == state.value or current.get("id") in wanted
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
