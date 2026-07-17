"""Shared Podium issue-row creation primitive."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence


def insert_issue_row(
    connection: sqlite3.Connection,
    *,
    binding_name: str,
    title: str,
    description: str,
    created_at: str,
    base_branch: str,
    priority: str | None = None,
    preferred_agent: str | None = None,
    preferred_model: str | None = None,
    preferred_skill: str | None = None,
    reasoning_effort: str = "high",
    worktree_active: bool = False,
    approval_required: bool = False,
    approved: bool = False,
    auto_land: bool = False,
    hold: bool = False,
    scheduled_for: str | None = None,
    comments_md: str = "",
    external_id: str | None = None,
    origin: str = "operator",
    blocked_by: Sequence[int] = (),
    locks: Sequence[str] = (),
) -> int:
    """Insert one todo issue without committing the caller's transaction."""
    cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          preferred_model, preferred_skill, reasoning_effort, worktree_active,
          approval_required, approved, auto_land, hold, scheduled_for,
          base_branch, comments_md, context_md, external_id, origin,
          blocked_by, locks, created_at, updated_at
        ) VALUES (?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '',
                  ?, ?, ?, ?, ?, ?)
        """,
        (
            binding_name,
            title,
            description,
            priority,
            preferred_agent,
            preferred_model,
            preferred_skill,
            reasoning_effort,
            worktree_active,
            approval_required,
            approved,
            auto_land,
            hold,
            scheduled_for,
            base_branch,
            comments_md,
            external_id,
            origin,
            json.dumps(list(blocked_by)),
            json.dumps(list(locks)),
            created_at,
            created_at,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("insert did not return an issue id")
    return int(cursor.lastrowid)
