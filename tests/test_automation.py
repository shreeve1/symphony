"""Pure automation helper tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation import (  # noqa: E402
    compute_next_fire,
    count_loop_iterations,
    loop_iteration_marker,
    render_template,
)


def test_count_loop_iterations_uses_durable_markers():
    comments = f"{loop_iteration_marker(1)}\n\nnoise\n\n{loop_iteration_marker(2)}"
    assert count_loop_iterations(comments) == 2
    assert count_loop_iterations(None) == 0


def test_render_template_replaces_supported_placeholders_only():
    assert (
        render_template(
            "Check {binding} every {interval}s; keep {other}", "homelab", 3600
        )
        == "Check homelab every 3600s; keep {other}"
    )


def test_compute_next_fire_starts_from_now():
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    assert compute_next_fire(3600, now=now) == "2026-07-17T13:00:00+00:00"


def test_compute_next_fire_preserves_overdue_cadence():
    now = datetime(2026, 7, 17, 14, tzinfo=UTC)
    assert (
        compute_next_fire(
            3600,
            current_next_fire_at="2026-07-17T08:00:00+00:00",
            now=now,
        )
        == "2026-07-17T09:00:00+00:00"
    )


def test_compute_next_fire_rejects_nonpositive_interval():
    with pytest.raises(ValueError, match="must be positive"):
        compute_next_fire(0, now=datetime(2026, 7, 17, tzinfo=UTC))
