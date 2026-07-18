"""Pure text helpers for review reland / commit-redispatch marker generation.

Leaf module — no __init__ dependency to avoid import cycles.
"""

from __future__ import annotations

import re
import shlex
from datetime import datetime
from importlib import import_module
from typing import cast

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


def _next_review_dispatch_marker(comments_md: str) -> str:
    prior = len(_REVIEW_DISPATCH_MARKER_RE.findall(comments_md or ""))
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


def _review_worktree_is_dirty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
) -> bool:
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(
            bool,
            remote_worktree.worktree_is_dirty(
                binding.remote, config.homelab_repo_path, binding_name, issue_id
            ),
        )
    worktree_helpers = import_module("worktree_facade")
    return cast(
        bool,
        worktree_helpers.worktree_is_dirty(
            config.homelab_repo_path, binding_name, issue_id
        ),
    )


def _review_worktree_diff_empty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> bool:
    if binding is not None and binding.is_remote:
        return False
    worktree_helpers = import_module("worktree_facade")
    return cast(
        bool,
        worktree_helpers.worktree_diff_empty(
            config.homelab_repo_path, binding_name, issue_id, base_branch
        ),
    )


def _review_base_repo_dirty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
) -> bool:
    """Return True if the base repo checkout has uncommitted changes.

    Mirror of `_review_worktree_is_dirty` that checks the base repo
    rather than a specific worktree. Local path uses
    ``web.api.worktree.base_repo_dirty`` directly because
    ``worktree_facade.__all__`` does not export it.
    """
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(
            bool,
            remote_worktree.base_repo_dirty(binding.remote, config.homelab_repo_path),
        )
    from web.api.worktree import base_repo_dirty as _local_base_repo_dirty

    return _local_base_repo_dirty(config.homelab_repo_path)


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
    Local path uses ``git rev-parse --abbrev-ref HEAD`` directly because the
    helper is base-checkout-specific (no worktree path needed).
    """
    if not base_branch:
        return True  # unknown target; caller should have set it; don't false-block
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        result = remote_worktree._run(
            binding.remote,
            f"git -C {shlex.quote(str(config.homelab_repo_path))} rev-parse --abbrev-ref HEAD",
            check=False,
        )
        return bool(result.stdout.strip() == base_branch)
    from web.api.worktree import _run_git as _local_run_git

    out = _local_run_git(
        config.homelab_repo_path, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
    )
    return bool(out and out.strip() == base_branch)


def _land_review_worktree(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> str | None:
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(
            str | None,
            remote_worktree.land_worktree(
                binding.remote,
                config.homelab_repo_path,
                binding_name,
                issue_id,
                base_branch,
            ),
        )
    worktree_helpers = import_module("worktree_facade")
    return cast(
        str | None,
        worktree_helpers.land_worktree(
            config.homelab_repo_path, binding_name, issue_id, base_branch
        ),
    )
