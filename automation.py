"""Pure helpers for binding automations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

LOOP_ITERATION_PREFIX = "### Symphony Loop Iteration"
LOOP_COMPLETE_PREFIX = "### Symphony Loop Complete"
LOOP_CAP_PREFIX = "### Symphony Loop Cap Reached"


def count_loop_iterations(comments_md: str | None) -> int:
    """Count loop iterations from their durable comment markers."""
    return (comments_md or "").count(LOOP_ITERATION_PREFIX)


def loop_iteration_marker(iteration: int) -> str:
    return f"{LOOP_ITERATION_PREFIX} · {iteration}"


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
