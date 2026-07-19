"""Pure text helpers for review reland / commit-redispatch marker generation.

Leaf module — no __init__ dependency to avoid import cycles.
"""

from __future__ import annotations

import re
from datetime import datetime
from importlib import import_module

from config import ProjectBinding, SymphonyConfig
from redispatch_core import (
    COMMIT_REDISPATCH_REPLY_PREFIX,
    RELAND_DONE_PREFIX,
    RELAND_DONE_RE,
    RELAND_PENDING_PREFIX,
    RELAND_PENDING_RE,
    redispatch_commit_note,
)

_REVIEW_DISPATCH_MARKER_RE = re.compile(
    r"^### Symphony Review(?: \((\d+)\))?[ \t]*$", re.MULTILINE
)


def _review_dispatch_marker_count(comments_md: str) -> int:
    return len(_REVIEW_DISPATCH_MARKER_RE.findall(comments_md or ""))


def _next_review_dispatch_marker(comments_md: str) -> str:
    prior = _review_dispatch_marker_count(comments_md)
    return f"### Symphony Review ({prior + 1})\n\nReview run dispatched."


def _reland_pending_count(comments_md: str) -> int:
    return len(RELAND_PENDING_RE.findall(comments_md or ""))


def _reland_done_count(comments_md: str) -> int:
    return len(RELAND_DONE_RE.findall(comments_md or ""))


def _commit_redispatch_body(
    config: SymphonyConfig,
    binding_name: str,
    issue_id: str,
    *,
    auto_land: bool,
    now: datetime,
) -> str:
    worktree_helpers = import_module("worktree_facade")
    worktree_path = worktree_helpers.worktree_dir(
        config.homelab_repo_path, binding_name, issue_id
    )
    branch = worktree_helpers.branch_name(binding_name, issue_id)
    body = (
        f"{COMMIT_REDISPATCH_REPLY_PREFIX} · {now.isoformat()})\n\n"
        f"{redispatch_commit_note(worktree_path, branch)}"
    )
    if auto_land:
        body += f"\n\n{RELAND_PENDING_PREFIX} · {now.isoformat()}"
    return body


def _commit_redispatch_body_base(
    config: SymphonyConfig,
    binding_name: str,
    *,
    now: datetime,
) -> str:
    """Re-dispatch body for a worktree-off spawn with a dirty base checkout.

    Distinct from ``_commit_redispatch_body`` (the worktree-merge path) because
    worktree-off spawns have no per-Issue worktree or branch: the agent commits
    directly to the binding's base checkout / base branch. The instruction must
    point at ``config.homelab_repo_path`` (not a worktree path) and tell the
    agent not to create a new branch — creating one would orphan the commit
    and the base would still appear dirty after the agent finishes.
    """
    repo_path = config.homelab_repo_path
    return (
        f"{COMMIT_REDISPATCH_REPLY_PREFIX} · {now.isoformat()})\n\n"
        f"The base checkout at `{repo_path}` for binding `{binding_name}` has "
        f"uncommitted changes, but the Issue was marked done with nothing "
        f"committed — so the work cannot be landed and would be lost.\n\n"
        f"Commit only the work that already exists in the base checkout. "
        f"First inspect `git status` to confirm every modified file belongs "
        f"to this Issue; do NOT use `git add -A` (the shared base checkout "
        f"may contain unrelated operator WIP). Stage each Issue-related file "
        f"explicitly with `git add <path>`, run the repo's tests for the "
        f"changed code, then `git commit` on the base branch with a clear "
        f"message. Do not start new work, expand scope, or create a new "
        f"branch. When the commit lands, end your turn."
    )


def _reland_done_body(comments_md: str, *, now: datetime) -> str:
    outstanding = _reland_pending_count(comments_md) - _reland_done_count(comments_md)
    if outstanding <= 0:
        return ""
    return "\n".join(
        f"{RELAND_DONE_PREFIX} · {now.isoformat()}" for _ in range(outstanding)
    )


# ---------------------------------------------------------------------------
# Impure worktree helpers (slice 2b)
# ---------------------------------------------------------------------------


def _review_backend(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
):
    """Pick the review/reland worktree backend once (local vs remote).

    Concentrates the ``binding.is_remote`` dispatch that the five helpers below
    used to repeat. Twin of the async ``worktree_backend_for`` seam (#503).
    """
    backend_mod = import_module("web.api.worktree_backend")
    remote = binding.remote if (binding is not None and binding.is_remote) else None
    return backend_mod.review_worktree_backend_for(
        config.homelab_repo_path, binding_name, issue_id, remote
    )


def _review_worktree_is_dirty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
) -> bool:
    return _review_backend(config, binding, binding_name, issue_id).is_dirty()


def _review_worktree_diff_empty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> bool:
    return _review_backend(config, binding, binding_name, issue_id).diff_empty(
        base_branch
    )


def _review_base_repo_dirty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
) -> bool:
    """Return True if the base repo checkout has uncommitted changes.

    Base-repo check (not worktree-specific), so binding_name/issue_id are
    irrelevant to the backend's base ops.
    """
    return _review_backend(config, binding, "", "").base_dirty()


def _review_base_repo_branch(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    base_branch: str,
) -> bool:
    """Return True if the base repo HEAD is currently on ``base_branch``.

    Guard against a worktree-off agent committing on a stale branch (e.g. one
    left behind by a previous worktree-merge land or a manually-checked-out
    feature branch). A clean checkout on the wrong branch is a degenerate
    state: closing the Issue to done would record a verdict on work that
    landed elsewhere, so the spawn-worktree-off land path must reject it.
    """
    return _review_backend(config, binding, "", "").base_on_branch(base_branch)


def _land_review_worktree(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> str | None:
    return _review_backend(config, binding, binding_name, issue_id).land(base_branch)
