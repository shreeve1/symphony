from __future__ import annotations

from pathlib import Path

from redispatch_core import (
    COMMIT_REDISPATCH_REPLY_PREFIX,
    RELAND_DONE_PREFIX,
    RELAND_DONE_RE,
    RELAND_PENDING_PREFIX,
    RELAND_PENDING_RE,
    count_commit_redispatches,
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
