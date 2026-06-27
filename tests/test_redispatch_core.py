from __future__ import annotations

from datetime import datetime
from pathlib import Path

from redispatch_core import (
    COMMIT_REDISPATCH_REPLY_PREFIX,
    OPERATOR_RELAND_DONE_RE,
    OPERATOR_RELAND_PENDING_PREFIX,
    OPERATOR_RELAND_PENDING_RE,
    RELAND_DONE_PREFIX,
    RELAND_DONE_RE,
    RELAND_PENDING_PREFIX,
    RELAND_PENDING_RE,
    count_commit_redispatches,
    count_operator_reland_pending,
    operator_reland_done_body,
    operator_reland_unconsumed,
    redispatch_commit_note,
)


def test_count_commit_redispatches_handles_empty_comments() -> None:
    assert count_commit_redispatches(None) == 0
    assert count_commit_redispatches("") == 0
    assert count_commit_redispatches("ordinary operator comment") == 0


def test_count_commit_redispatches_counts_existing_markers() -> None:
    comments_md = "\n\n".join(
        f"{COMMIT_REDISPATCH_REPLY_PREFIX} · 2026-06-1{n})\n\nbody" for n in range(2)
    )

    assert count_commit_redispatches(comments_md) == 2


def test_reland_marker_regexes_count_pending_and_done_headings() -> None:
    comments_md = "\n".join(
        [
            "intro",
            f"{RELAND_PENDING_PREFIX}",
            f"{RELAND_PENDING_PREFIX} · 2026-06-24T00:00:00+00:00",
            f"{RELAND_DONE_PREFIX}",
            f"not a heading {RELAND_DONE_PREFIX}",
        ]
    )

    assert len(RELAND_PENDING_RE.findall(comments_md)) == 2
    assert len(RELAND_DONE_RE.findall(comments_md)) == 1


def test_operator_reland_marker_distinct_from_review_reland_prefix() -> None:
    """The operator move-to-done reland marker is DISTINCT from the review
    RELAND pair so tracker_podium.list_candidates (which keys review-run
    reselection off RELAND_PENDING_RE) does NOT reselect on it (finding #3)."""
    now = datetime(2026, 6, 27, 0, 0, 0)
    md = "\n".join(
        [
            "intro",
            f"{OPERATOR_RELAND_PENDING_PREFIX} · {now.isoformat()}",
            f"{OPERATOR_RELAND_PENDING_PREFIX} · {now.isoformat()}",
            f"not a heading {OPERATOR_RELAND_PENDING_PREFIX}",
        ]
    )

    # Operator side: counts + unconsumed + done-body balancing.
    assert len(OPERATOR_RELAND_PENDING_RE.findall(md)) == 2
    assert count_operator_reland_pending(md) == 2
    assert operator_reland_unconsumed(md) is True
    balanced = md + "\n" + operator_reland_done_body(md, now=now)
    assert len(OPERATOR_RELAND_DONE_RE.findall(balanced)) == 2
    assert operator_reland_unconsumed(balanced) is False

    # Review side: the exact reselection expression list_candidates uses must
    # NOT count the operator marker as a review reland.
    assert len(RELAND_PENDING_RE.findall(md)) == 0
    assert not (len(RELAND_PENDING_RE.findall(md)) > len(RELAND_DONE_RE.findall(md)))
    # And the operator marker never matches the review prefix.
    assert len(OPERATOR_RELAND_PENDING_RE.findall(f"{RELAND_PENDING_PREFIX}")) == 0


def test_redispatch_commit_note_formats_existing_instruction_body() -> None:
    assert redispatch_commit_note(
        Path("worktrees/trading/123"), "podium/trading/123"
    ) == (
        "Your worktree at `worktrees/trading/123` (branch `podium/trading/123`) "
        "has uncommitted changes, but the Issue was marked done with nothing "
        "committed — so the work cannot be landed and would be lost.\n\n"
        "Commit only the work that already exists in the worktree: run the repo's "
        "tests for the changed code, then `git add -A && git commit` with a clear "
        "message. Do not start new work or expand scope. When the commit lands, "
        "end your turn."
    )
