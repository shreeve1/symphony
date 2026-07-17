"""Pure helpers for binding automations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

LOOP_ITERATION_PREFIX = "### Symphony Loop Iteration"
LOOP_COMPLETE_PREFIX = "### Symphony Loop Complete"
LOOP_CAP_PREFIX = "### Symphony Loop Cap Reached"
# Issue #8 — loop failure retry (ADR-0041). A blocked loop iteration is
# re-dispatched up to MAX_LOOP_RETRIES consecutive times; on the Nth
# consecutive block the loop terminates with LOOP_BLOCKED_PREFIX and the
# automation is disabled.
LOOP_RETRY_PREFIX = "### Symphony Loop Retry"
LOOP_BLOCKED_PREFIX = "### Symphony Loop Blocked"
MAX_LOOP_RETRIES = 3


def count_loop_iterations(comments_md: str | None) -> int:
    """Count loop iterations from their durable comment markers."""
    return (comments_md or "").count(LOOP_ITERATION_PREFIX)


def count_loop_retries(comments_md: str | None) -> int:
    """Count consecutive loop retry markers from durable comment markers.

    Resets to zero after any successful (in_review) iteration marker, so the
    retry budget tracks the *most recent* consecutive-failure run rather than
    the historical total. Mirrors `count_commit_redispatches` style.
    """
    if not comments_md:
        return 0
    # The most recent productive iteration marker resets the consecutive run.
    last_iteration = comments_md.rfind(LOOP_ITERATION_PREFIX)
    tail = comments_md[last_iteration:] if last_iteration != -1 else comments_md
    return tail.count(LOOP_RETRY_PREFIX)


def loop_iteration_marker(iteration: int) -> str:
    return f"{LOOP_ITERATION_PREFIX} · {iteration}"


def loop_retry_marker(now: datetime) -> str:
    """Render the durable marker used by the loop reconciler on re-dispatch."""
    return f"{LOOP_RETRY_PREFIX} · {now.isoformat()}"


def loop_blocked_marker(failures: int, now: datetime) -> str:
    """Render the terminal marker when the retry budget is exhausted."""
    return (
        f"{LOOP_BLOCKED_PREFIX} · {failures} consecutive failures · {now.isoformat()}\n\n"
        f"Loop terminated after {failures} consecutive blocked iterations; "
        "worktree preserved for operator review."
    )


def loop_instructions(completion_marker: str) -> str:
    return (
        "## Symphony Loop\n\n"
        "Each iteration starts with fresh agent context; the worktree is the only "
        "memory. Record progress in the worktree, and create "
        f"`{completion_marker}` only when the task is complete."
    )


def render_template(template: str, binding_name: str, interval_seconds: int) -> str:
    """Replace supported placeholders and preserve unknown ones."""
    return template.replace("{binding}", binding_name).replace(
        "{interval}", str(interval_seconds)
    )


def compute_next_fire(
    interval_seconds: int,
    *,
    current_next_fire_at: str | None = None,
    now: datetime | None = None,
) -> str:
    """Advance from the scheduled fire time, or from now on first fire."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    base = now or datetime.now(UTC)
    if current_next_fire_at is not None:
        base = datetime.fromisoformat(current_next_fire_at)
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
    return (base + timedelta(seconds=interval_seconds)).isoformat()
