"""Process-neutral commit redispatch helpers.

Keep this module pure so independent processes can share marker vocabulary
without importing each other's scaffolding.
"""

from __future__ import annotations

import re
from os import PathLike
from typing import Any

MAX_COMMIT_REDISPATCH = 2
RETRY_MARKER_PREFIX = "### Symphony Retry (transient"

# Substring used both as the synthetic operator-reply header and as the marker
# counted to enforce MAX_COMMIT_REDISPATCH. Must keep the `### Operator Reply (`
# shape so prompt_renderer's operator-reply regex surfaces it on resume.
COMMIT_REDISPATCH_REPLY_PREFIX = "### Operator Reply (Symphony auto-commit"

RELAND_PENDING_PREFIX = "### Symphony Reland Pending"
RELAND_DONE_PREFIX = "### Symphony Reland Done"
RELAND_PENDING_RE = re.compile(
    rf"^{re.escape(RELAND_PENDING_PREFIX)}(?:\s|$)", re.MULTILINE
)
RELAND_DONE_RE = re.compile(rf"^{re.escape(RELAND_DONE_PREFIX)}(?:\s|$)", re.MULTILINE)


def count_commit_redispatches(comments_md: str | None) -> int:
    """Count prior auto-commit re-dispatches recorded in ``comments_md``."""
    if not comments_md:
        return 0
    return comments_md.count(COMMIT_REDISPATCH_REPLY_PREFIX)


def redispatch_commit_note(worktree_path: str | PathLike[Any], branch: str) -> str:
    """Instruction body for a dirty-worktree commit re-dispatch note."""
    return (
        f"Your worktree at `{worktree_path}` (branch `{branch}`) has uncommitted "
        f"changes, but the Issue was marked done with nothing committed — so "
        f"the work cannot be landed and would be lost.\n\n"
        f"Commit only the work that already exists in the worktree: run the "
        f"repo's tests for the changed code, then `git add -A && git commit` "
        f"with a clear message. Do not start new work or expand scope. When the "
        f"commit lands, end your turn."
    )
