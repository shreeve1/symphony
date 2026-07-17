"""Pure spawn-automation helper tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation import compute_next_fire, render_template  # noqa: E402


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
