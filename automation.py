"""Pure helpers for spawn-mode automations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


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
