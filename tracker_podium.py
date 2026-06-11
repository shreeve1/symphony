"""Podium SQLite implementation of the Symphony TrackerAdapter.

Podium is the source of truth for coding bindings: issue states project onto
``issue.state`` enum values, mode roles project from ``issue.preferred_skill``
through ``skill_mode_map``, and agent roles project from
``issue.preferred_agent``. Approval, approved, and scheduled roles are absent
for coding bindings because Podium has no columns for them yet; infra-binding
projection is deferred to #023c, where ``approval_required``, ``approved``, and
``scheduled_for`` columns will be added.

Labels are intentionally dropped in Podium. ``add_label`` / ``remove_label``
and their plural forms are no-ops that return the current issue row.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skill_mode_map import mode_for_skill
from tracker_contract import (
    DEFAULT_CONTRACT,
    PlaneLabel,
    PlaneState,
    RoleBinding,
    TrackerContract,
    TrackerRole,
    coerce_state_role,
)
from web.api.db import resolve_db_path


PAGE_SIZE = 50
MAX_PAGES_PER_TICK = 3


@dataclass(frozen=True)
class CandidateIssue:
    id: str
    identifier: str
    name: str
    description: str
    labels: tuple[str, ...]
    created_at: str
    schedule_not_before: str = ""
    schedule_not_after: str = ""
    schedule_reason: str = ""
    schedule_source: str = ""
    schedule_late: str = ""
    comments_md: str = ""
    context_md: str = ""
    preferred_skill: str | None = None


PODIUM_STATE_BY_ROLE: dict[TrackerRole, str] = {
    TrackerRole.STATE_TODO: "todo",
    TrackerRole.STATE_RUNNING: "running",
    TrackerRole.STATE_IN_REVIEW: "in_review",
    TrackerRole.STATE_BLOCKED: "blocked",
    TrackerRole.STATE_DONE: "done",
}

PODIUM_CONTRACT = replace(
    DEFAULT_CONTRACT,
    state_roles={role: RoleBinding(value, value) for role, value in PODIUM_STATE_BY_ROLE.items()},
)


@dataclass
class PodiumTrackerAdapter:
    """TrackerAdapter backed by the Podium SQLite database."""

    stores_context: bool = True
    db_path: Path | None = None
    binding_name: str | None = None
    contract: TrackerContract = field(default_factory=lambda: PODIUM_CONTRACT)

    def __post_init__(self) -> None:
        if self.contract is not PODIUM_CONTRACT:
            self.contract = replace(
                self.contract,
                state_roles={role: RoleBinding(value, value) for role, value in PODIUM_STATE_BY_ROLE.items()},
            )

    def connect(self) -> sqlite3.Connection:
        path = self.db_path or resolve_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _state_value(self, state: PlaneState | TrackerRole) -> str:
        return PODIUM_STATE_BY_ROLE[coerce_state_role(state)]

    def _row_to_issue(self, row: sqlite3.Row) -> dict[str, Any]:
        issue = dict(row)
        issue["id"] = str(issue["id"])
        issue["identifier"] = str(issue["id"])
        issue["sequence_id"] = str(issue["id"])
        issue["name"] = issue.get("title") or ""
        issue["description_html"] = issue.get("description") or ""
        issue["description"] = issue.get("description") or ""
        issue["labels"] = list(self.issue_labels(issue))
        return issue

    def issue_labels(self, issue: dict[str, Any]) -> tuple[str, ...]:
        labels: list[str] = []
        mode = mode_for_skill(issue.get("preferred_skill"))
        if mode == "plan":
            labels.append(self.contract.label_name_for_role(TrackerRole.MODE_PLAN))
        elif mode == "build":
            labels.append(self.contract.label_name_for_role(TrackerRole.MODE_BUILD))
        preferred_agent = issue.get("preferred_agent")
        if preferred_agent:
            labels.append(f"agent:{preferred_agent}")
        return tuple(labels)

    def issue_is_state(self, issue: dict[str, Any], state: TrackerRole) -> bool:
        return str(issue.get("state") or "") == PODIUM_STATE_BY_ROLE[state]

    def labels_contain_role(self, labels: tuple[str, ...] | list[str], role: TrackerRole) -> bool:
        if role in {TrackerRole.APPROVAL_REQUIRED, TrackerRole.APPROVED, TrackerRole.SCHEDULED, TrackerRole.HAS_WORKTREE}:
            return False
        binding = self.contract.optional_label_binding(role)
        return bool(binding and binding.name in set(labels))

    async def list_candidates(self) -> list[CandidateIssue]:
        candidates = []
        for issue in await self.list_issues_by_state(TrackerRole.STATE_TODO):
            candidates.append(
                CandidateIssue(
                    id=str(issue["id"]),
                    identifier=str(issue.get("identifier") or issue["id"]),
                    name=str(issue.get("name") or ""),
                    description=str(issue.get("description") or ""),
                    labels=tuple(issue.get("labels") or ()),
                    created_at=str(issue.get("created_at") or ""),
                    comments_md=str(issue.get("comments_md") or ""),
                    context_md=str(issue.get("context_md") or ""),
                    preferred_skill=issue.get("preferred_skill"),
                )
            )
        return candidates

    async def list_issues(
        self,
        state_filter: PlaneState | TrackerRole | None = None,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]:
        limit = max(0, per_page * max_pages)
        with self.connect() as connection:
            if self.binding_name is not None and state_filter is not None:
                rows = connection.execute(
                    """
                    SELECT * FROM issue
                    WHERE binding_name = ? AND state = ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (self.binding_name, self._state_value(state_filter), limit),
                ).fetchall()
            elif self.binding_name is not None:
                rows = connection.execute(
                    """
                    SELECT * FROM issue
                    WHERE binding_name = ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (self.binding_name, limit),
                ).fetchall()
            elif state_filter is not None:
                rows = connection.execute(
                    """
                    SELECT * FROM issue
                    WHERE state = ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (self._state_value(state_filter), limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM issue
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row_to_issue(row) for row in rows]

    async def list_issues_by_state(
        self,
        state: PlaneState | TrackerRole,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]:
        return await self.list_issues(state, per_page=per_page, max_pages=max_pages)

    async def get_issue(self, issue_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
        if row is None:
            raise KeyError(f"Podium issue not found: {issue_id}")
        return self._row_to_issue(row)

    async def list_comments(self, issue_id: str, *, max_pages: int = MAX_PAGES_PER_TICK) -> list[dict[str, Any]]:
        issue = await self.get_issue(issue_id)
        body = str(issue.get("comments_md") or "").strip()
        if not body:
            return []
        return [{"id": f"podium-comments-{issue_id}", "created_at": issue.get("updated_at") or "", "body": body, "comment_html": body}]

    async def add_comment(self, issue_id: str, comment: Any) -> dict[str, Any]:
        return await self.post_comment(issue_id, comment.render())

    async def post_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        block = _append_block("### Symphony AI Summary", body)
        return await self._append_issue_field(issue_id, "comments_md", block)

    async def append_context(self, issue_id: str, body: str) -> dict[str, Any]:
        block = _append_block("### Symphony Context Append", body)
        return await self._append_issue_field(issue_id, "context_md", block)

    async def transition_state(self, issue_id: str, state: PlaneState | TrackerRole) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "UPDATE issue SET state = ?, updated_at = ? WHERE id = ?",
                (self._state_value(state), _now(), issue_id),
            )
            connection.commit()
        return await self.get_issue(issue_id)

    async def add_label(self, issue_id: str, label: PlaneLabel | TrackerRole) -> dict[str, Any]:
        return await self.get_issue(issue_id)

    async def remove_label(self, issue_id: str, label: PlaneLabel | TrackerRole) -> dict[str, Any]:
        return await self.get_issue(issue_id)

    async def add_labels(self, issue_id: str, labels: list[PlaneLabel | TrackerRole]) -> dict[str, Any]:
        return await self.get_issue(issue_id)

    async def remove_labels(self, issue_id: str, labels: list[PlaneLabel | TrackerRole]) -> dict[str, Any]:
        return await self.get_issue(issue_id)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row is not None else None

    async def record_run(self, run_row: dict[str, Any]) -> dict[str, Any]:
        if not any(key in run_row for key in _RUN_INSERT_COLUMNS):
            raise ValueError("record_run requires at least one run column")
        values = tuple(run_row.get(key) for key in _RUN_INSERT_COLUMNS)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO run(
                  issue_id, agent, provider, model, state, verdict, summary,
                  exit_code, cost_usd, input_tokens, output_tokens, worktree_path,
                  branch_name, base_branch, log_path, skill_invoked, started_at,
                  ended_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            run_id = cursor.lastrowid
            row = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
            assert row is not None
            self._update_issue_run_projection(connection, row)
            connection.commit()
        row = await self.get_run(str(run_id))
        assert row is not None
        return row

    async def update_run(self, run_id: str, run_row: dict[str, Any]) -> dict[str, Any]:
        updates = {key: run_row[key] for key in _RUN_UPDATE_COLUMNS if key in run_row}
        if not updates:
            raise ValueError("update_run requires at least one run column")
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = tuple(updates.values())
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
            if existing is None:
                raise KeyError(f"Podium run not found: {run_id}")
            connection.execute(
                f"UPDATE run SET {assignments} WHERE id = ?",
                (*values, run_id),
            )
            row = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
            assert row is not None
            self._update_issue_run_projection(connection, row)
            connection.commit()
        return dict(row)

    def _update_issue_run_projection(self, connection: sqlite3.Connection, row: sqlite3.Row) -> None:
        issue_id = row["issue_id"]
        if issue_id is None:
            return
        connection.execute(
            "UPDATE issue SET latest_run_id = ?, latest_run_state = ?, latest_verdict = ?, last_event_at = ?, updated_at = ? WHERE id = ?",
            (
                row["id"],
                row["state"],
                row["verdict"],
                row["ended_at"] or row["started_at"] or _now(),
                _now(),
                issue_id,
            ),
        )

    async def _append_issue_field(self, issue_id: str, field_name: str, block: str) -> dict[str, Any]:
        if field_name == "comments_md":
            return await self._append_comments(issue_id, block)
        if field_name == "context_md":
            return await self._append_context(issue_id, block)
        raise ValueError(f"unsupported issue field: {field_name}")

    async def _append_comments(self, issue_id: str, block: str) -> dict[str, Any]:
        with self.connect() as connection:
            current = connection.execute("SELECT comments_md FROM issue WHERE id = ?", (issue_id,)).fetchone()
            if current is None:
                raise KeyError(f"Podium issue not found: {issue_id}")
            existing = str(current["comments_md"] or "").rstrip()
            updated = f"{existing}\n\n{block}".strip() if existing else block
            connection.execute(
                "UPDATE issue SET comments_md = ?, updated_at = ? WHERE id = ?",
                (updated, _now(), issue_id),
            )
            connection.commit()
        return await self.get_issue(issue_id)

    async def _append_context(self, issue_id: str, block: str) -> dict[str, Any]:
        with self.connect() as connection:
            current = connection.execute("SELECT context_md FROM issue WHERE id = ?", (issue_id,)).fetchone()
            if current is None:
                raise KeyError(f"Podium issue not found: {issue_id}")
            existing = str(current["context_md"] or "").rstrip()
            updated = f"{existing}\n\n{block}".strip() if existing else block
            connection.execute(
                "UPDATE issue SET context_md = ?, updated_at = ? WHERE id = ?",
                (updated, _now(), issue_id),
            )
            connection.commit()
        return await self.get_issue(issue_id)


_RUN_INSERT_COLUMNS = (
    "issue_id",
    "agent",
    "provider",
    "model",
    "state",
    "verdict",
    "summary",
    "exit_code",
    "cost_usd",
    "input_tokens",
    "output_tokens",
    "worktree_path",
    "branch_name",
    "base_branch",
    "log_path",
    "skill_invoked",
    "started_at",
    "ended_at",
)
_RUN_UPDATE_COLUMNS = tuple(key for key in _RUN_INSERT_COLUMNS if key != "issue_id")


def _append_block(title: str, body: str) -> str:
    return f"{title}\n\n{body.strip()}".strip()


def _now() -> str:
    return datetime.now(UTC).isoformat()
