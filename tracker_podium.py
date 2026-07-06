"""Podium SQLite implementation of the Symphony TrackerAdapter.

Podium is the source of truth for coding bindings: issue states project onto
``issue.state`` enum values, mode roles project from ``issue.preferred_skill``
through ``skill_mode_map``, and agent roles project from
``issue.preferred_agent``. Infra-binding approval and schedule roles project
onto ``issue.approval_required``, ``issue.approved``, and due
``issue.scheduled_for`` values.

Labels are intentionally dropped in Podium except for infra role projection.
``add_label`` / ``remove_label`` and their plural forms mutate only the
projected infra columns; other labels remain no-ops that return the current
issue row.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from redispatch_core import RELAND_DONE_RE, RELAND_PENDING_RE, retry_cooldown_expired
from skill_mode_map import mode_for_skill
from tracker_contract import (
    DEFAULT_CONTRACT,
    RoleBinding,
    TrackerContract,
    TrackerLabel,
    TrackerRole,
    TrackerState,
    coerce_label_role,
    coerce_state_role,
)
from tracker_types import CandidateIssue
from web.api.db import resolve_db_path

PAGE_SIZE = 50
MAX_PAGES_PER_TICK = 3
LOGGER = logging.getLogger(__name__)
DEPENDENCY_DONE_STATES = {"done", "archived"}
REVIEW_MARKER_RE = re.compile(
    r"^### Symphony Review(?: \((\d+)\))?[ \t]*$", re.MULTILINE
)


PODIUM_STATE_BY_ROLE: dict[TrackerRole, str] = {
    TrackerRole.STATE_TODO: "todo",
    TrackerRole.STATE_RUNNING: "running",
    TrackerRole.STATE_IN_REVIEW: "in_review",
    TrackerRole.STATE_BLOCKED: "blocked",
    TrackerRole.STATE_DONE: "done",
}

PODIUM_CONTRACT = replace(
    DEFAULT_CONTRACT,
    state_roles={
        role: RoleBinding(value, value) for role, value in PODIUM_STATE_BY_ROLE.items()
    },
)


@dataclass
class PodiumTrackerAdapter:
    """TrackerAdapter backed by the Podium SQLite database."""

    stores_context: bool = True
    db_path: Path | None = None
    binding_name: str | None = None
    contract: TrackerContract = field(default_factory=lambda: PODIUM_CONTRACT)

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = resolve_db_path()
        if self.contract is not PODIUM_CONTRACT:
            self.contract = replace(
                self.contract,
                state_roles={
                    role: RoleBinding(value, value)
                    for role, value in PODIUM_STATE_BY_ROLE.items()
                },
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

    def _state_value(self, state: TrackerState | TrackerRole) -> str:
        return PODIUM_STATE_BY_ROLE[coerce_state_role(state)]

    def _row_to_issue(self, row: sqlite3.Row) -> dict[str, Any]:
        issue = dict(row)
        issue["id"] = str(issue["id"])
        issue["identifier"] = str(issue["id"])
        issue["sequence_id"] = str(issue["id"])
        issue["name"] = issue.get("title") or ""
        issue["description_html"] = issue.get("description") or ""
        issue["description"] = issue.get("description") or ""
        issue["auto_land"] = bool(issue.get("auto_land") or False)
        issue["blocked_by"] = _json_list(issue.get("blocked_by"), int)
        issue["locks"] = _json_list(issue.get("locks"), str)
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
        if issue.get("approval_required"):
            approval_required = self.contract.optional_label_name_for_role(
                TrackerRole.APPROVAL_REQUIRED
            )
            if approval_required:
                labels.append(approval_required)
        if issue.get("approved"):
            approved = self.contract.optional_label_name_for_role(TrackerRole.APPROVED)
            if approved:
                labels.append(approved)
        if _scheduled_due(issue.get("scheduled_for")):
            scheduled = self.contract.optional_label_name_for_role(
                TrackerRole.SCHEDULED
            )
            if scheduled:
                labels.append(scheduled)
        return tuple(labels)

    def issue_is_state(self, issue: dict[str, Any], state: TrackerRole) -> bool:
        return str(issue.get("state") or "") == PODIUM_STATE_BY_ROLE[state]

    def labels_contain_role(
        self, labels: tuple[str, ...] | list[str], role: TrackerRole
    ) -> bool:
        binding = self.contract.optional_label_binding(role)
        return bool(binding and binding.name in set(labels))

    def skill_source(self, skill_name: str) -> str:
        """Absolute SKILL.md path for a catalog skill, or "" when unknown.

        Deterministic: prefers binding-scoped skills, then global (null
        binding_name), then falls back to any match by id.  This avoids
        picking a stale row from a different host.
        """
        with self.connect() as connection:
            row = connection.execute(
                "SELECT source FROM skill WHERE name = ? "
                "ORDER BY CASE WHEN binding_name = ? THEN 0 "
                "WHEN binding_name IS NULL THEN 1 ELSE 2 END, id",
                (skill_name, self.binding_name),
            ).fetchone()
        return str(row["source"]) if row and row["source"] else ""

    async def list_candidates(self) -> list[CandidateIssue]:
        candidates = []
        issues = await self._list_candidate_snapshot()
        state_by_id = {
            str(issue["id"]): str(issue.get("state") or "") for issue in issues
        }
        for issue in issues:
            is_todo = self.issue_is_state(issue, TrackerRole.STATE_TODO)
            is_review = self.issue_is_state(issue, TrackerRole.STATE_IN_REVIEW)
            comments_md = str(issue.get("comments_md") or "")
            reland_unconsumed = len(RELAND_PENDING_RE.findall(comments_md)) > len(
                RELAND_DONE_RE.findall(comments_md)
            )
            # Review runs only fire for slicer-authored (auto_land) issues — the
            # /podium-issues slicer guarantees an objectively-runnable
            # ## Verification, which is the trust basis for the unattended review
            # phase. Operator-authored issues (auto_land=false) skip review
            # entirely and stay in_review for a manual merge (issue #149; scopes
            # ADR-0023 #3's universal-for-coding review down to auto_land).
            review_dispatch = (
                is_review
                and bool(issue.get("auto_land") or False)
                and (
                    not REVIEW_MARKER_RE.search(comments_md)
                    or (
                        reland_unconsumed
                        and retry_cooldown_expired(comments_md, datetime.now(UTC))
                    )
                )
            )
            if not is_todo and not review_dispatch:
                continue
            if is_todo and not self._dependencies_satisfied(issue, state_by_id):
                continue
            # hold is an operator-only dispatch gate (never set by the slicer);
            # a held todo issue is not emitted as a candidate until cleared.
            if is_todo and bool(issue.get("hold") or False):
                continue
            preferred_skill = issue.get("preferred_skill")
            candidates.append(
                CandidateIssue(
                    id=str(issue["id"]),
                    identifier=str(issue.get("identifier") or issue["id"]),
                    name=str(issue.get("name") or ""),
                    description=str(issue.get("description") or ""),
                    labels=tuple(issue.get("labels") or ()),
                    created_at=str(issue.get("created_at") or ""),
                    comments_md=comments_md,
                    context_md=str(issue.get("context_md") or ""),
                    preferred_skill=preferred_skill,
                    worktree_active=bool(issue.get("worktree_active") or False),
                    base_branch=str(issue.get("base_branch") or ""),
                    binding_name=self.binding_name or "",
                    preferred_model=issue.get("preferred_model"),
                    reasoning_effort=str(issue.get("reasoning_effort") or "high"),
                    skill_source=(
                        self.skill_source(str(preferred_skill))
                        if preferred_skill
                        else ""
                    ),
                    locks=tuple(issue.get("locks") or ()),
                    review_dispatch=review_dispatch,
                    origin=str(issue.get("origin") or "operator"),
                )
            )
        return candidates

    async def _list_candidate_snapshot(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if self.binding_name is not None:
                rows = connection.execute(
                    """
                    SELECT * FROM issue
                    WHERE binding_name = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (self.binding_name,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM issue
                    ORDER BY created_at ASC, id ASC
                    """
                ).fetchall()
        return [self._row_to_issue(row) for row in rows]

    def _dependencies_satisfied(
        self, issue: dict[str, Any], state_by_id: dict[str, str]
    ) -> bool:
        for blocker_id in issue.get("blocked_by") or []:
            blocker_state = state_by_id.get(str(blocker_id))
            if blocker_state is None:
                LOGGER.warning(
                    "dependency_blocker_unresolved issue=%s blocker=%s",
                    issue["id"],
                    blocker_id,
                )
                continue
            if blocker_state not in DEPENDENCY_DONE_STATES:
                return False
        return True

    async def list_issues(
        self,
        state_filter: TrackerState | TrackerRole | None = None,
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
        state: TrackerState | TrackerRole,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]:
        return await self.list_issues(state, per_page=per_page, max_pages=max_pages)

    async def get_issue(self, issue_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Podium issue not found: {issue_id}")
        return self._row_to_issue(row)

    async def list_comments(
        self, issue_id: str, *, max_pages: int = MAX_PAGES_PER_TICK
    ) -> list[dict[str, Any]]:
        issue = await self.get_issue(issue_id)
        body = str(issue.get("comments_md") or "").strip()
        if not body:
            return []
        return [
            {
                "id": f"podium-comments-{issue_id}",
                "created_at": issue.get("updated_at") or "",
                "body": body,
                "comment_html": body,
            }
        ]

    async def add_comment(self, issue_id: str, comment: Any) -> dict[str, Any]:
        return await self.post_comment(issue_id, comment.render())

    async def post_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        return await self._append_issue_field(issue_id, "comments_md", body.strip())

    async def append_context(self, issue_id: str, body: str) -> dict[str, Any]:
        block = _append_block("### Symphony Context Append", body)
        return await self._append_issue_field(issue_id, "context_md", block)

    async def transition_state(
        self, issue_id: str, state: TrackerState | TrackerRole
    ) -> dict[str, Any]:
        next_state = self._state_value(state)
        with self.connect() as connection:
            if next_state in ("in_review", "blocked"):
                connection.execute(
                    """
                    UPDATE issue
                    SET state = ?, inbox_dismissed_at = NULL, updated_at = ?
                    WHERE id = ? AND state != 'archived'
                    """,
                    (next_state, _now(), issue_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE issue
                    SET state = ?, updated_at = ?
                    WHERE id = ? AND state != 'archived'
                    """,
                    (next_state, _now(), issue_id),
                )
            connection.commit()
        return await self.get_issue(issue_id)

    async def add_label(
        self, issue_id: str, label: TrackerLabel | TrackerRole
    ) -> dict[str, Any]:
        return await self.add_labels(issue_id, [label])

    async def remove_label(
        self, issue_id: str, label: TrackerLabel | TrackerRole
    ) -> dict[str, Any]:
        return await self.remove_labels(issue_id, [label])

    async def add_labels(
        self, issue_id: str, labels: list[TrackerLabel | TrackerRole]
    ) -> dict[str, Any]:
        updates = _infra_role_updates(labels, adding=True)
        if not updates:
            return await self.get_issue(issue_id)
        return await self._update_issue_columns(issue_id, updates)

    async def remove_labels(
        self, issue_id: str, labels: list[TrackerLabel | TrackerRole]
    ) -> dict[str, Any]:
        updates = _infra_role_updates(labels, adding=False)
        if not updates:
            return await self.get_issue(issue_id)
        return await self._update_issue_columns(issue_id, updates)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM run WHERE id = ?", (run_id,)
            ).fetchone()
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
                  ended_at, agent_session_sha, resumed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            run_id = cursor.lastrowid
            row = connection.execute(
                "SELECT * FROM run WHERE id = ?", (run_id,)
            ).fetchone()
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
            existing = connection.execute(
                "SELECT * FROM run WHERE id = ?", (run_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Podium run not found: {run_id}")
            connection.execute(
                f"UPDATE run SET {assignments} WHERE id = ?",
                (*values, run_id),
            )
            row = connection.execute(
                "SELECT * FROM run WHERE id = ?", (run_id,)
            ).fetchone()
            assert row is not None
            self._update_issue_run_projection(connection, row)
            connection.commit()
        return dict(row)

    async def reconcile_orphaned_runs(self, *, reaped_at: str | None = None) -> int:
        timestamp = reaped_at or _now()
        summary = f"restart-orphan: reaped at {timestamp}"
        comment = f"Run reaped on restart at {timestamp}; worktree preserved."
        with self.connect() as connection:
            if self.binding_name is not None:
                rows = connection.execute(
                    """
                    SELECT run.*
                    FROM run
                    JOIN issue ON issue.id = run.issue_id
                    WHERE run.state IN ('queued', 'running')
                      AND issue.binding_name = ?
                    ORDER BY run.id ASC
                    """,
                    (self.binding_name,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT run.*
                    FROM run
                    JOIN issue ON issue.id = run.issue_id
                    WHERE run.state IN ('queued', 'running')
                    ORDER BY run.id ASC
                    """
                ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE run
                    SET state = 'failed', verdict = 'blocked', summary = ?,
                        exit_code = COALESCE(exit_code, 1), ended_at = ?
                    WHERE id = ?
                    """,
                    (summary, timestamp, row["id"]),
                )
                updated_run = connection.execute(
                    "SELECT * FROM run WHERE id = ?", (row["id"],)
                ).fetchone()
                assert updated_run is not None
                self._update_issue_run_projection(connection, updated_run)
                current = connection.execute(
                    "SELECT comments_md FROM issue WHERE id = ?", (row["issue_id"],)
                ).fetchone()
                if current is not None:
                    existing = str(current["comments_md"] or "").rstrip()
                    block = _append_block("### Symphony AI Summary", comment)
                    updated_comments = (
                        f"{existing}\n\n{block}".strip() if existing else block
                    )
                    connection.execute(
                        """
                        UPDATE issue
                        SET state = 'blocked', comments_md = ?,
                            inbox_dismissed_at = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (updated_comments, timestamp, row["issue_id"]),
                    )
            connection.commit()
        return len(rows)

    async def prune_run_logs(
        self,
        *,
        now: datetime | None = None,
        max_age_days: int = 90,
        max_logs_per_issue: int = 100,
    ) -> int:
        cutoff = (now or datetime.now(UTC)) - timedelta(days=max_age_days)
        with self.connect() as connection:
            if self.binding_name is not None:
                rows = connection.execute(
                    """
                    SELECT run.id, run.issue_id, run.log_path
                    FROM run
                    JOIN issue ON issue.id = run.issue_id
                    WHERE run.log_path IS NOT NULL AND run.log_path != ''
                      AND issue.binding_name = ?
                    ORDER BY run.issue_id ASC, run.started_at DESC, run.id DESC
                    """,
                    (self.binding_name,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT run.id, run.issue_id, run.log_path
                    FROM run
                    JOIN issue ON issue.id = run.issue_id
                    WHERE run.log_path IS NOT NULL AND run.log_path != ''
                    ORDER BY run.issue_id ASC, run.started_at DESC, run.id DESC
                    """
                ).fetchall()
            rows_by_issue: dict[Any, list[sqlite3.Row]] = {}
            for row in rows:
                rows_by_issue.setdefault(row["issue_id"], []).append(row)

            reaped_run_ids: list[Any] = []
            for issue_rows in rows_by_issue.values():
                for index, row in enumerate(issue_rows):
                    path = Path(str(row["log_path"])).expanduser()
                    too_many = index >= max_logs_per_issue
                    too_old = False
                    if path.is_file():
                        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                        too_old = modified < cutoff
                    if not too_many and not too_old:
                        continue
                    if path.is_file():
                        path.unlink()
                    reaped_run_ids.append(row["id"])

            for run_id in reaped_run_ids:
                connection.execute(
                    "UPDATE run SET log_path = NULL WHERE id = ?", (run_id,)
                )
            connection.commit()
        return len(reaped_run_ids)

    def _update_issue_run_projection(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> None:
        issue_id = row["issue_id"]
        if issue_id is None:
            return
        verdict = (
            row["verdict"] if row["verdict"] in {"done", "review", "blocked"} else None
        )
        connection.execute(
            "UPDATE issue SET latest_run_id = ?, latest_run_state = ?, latest_verdict = ?, last_event_at = ?, updated_at = ? WHERE id = ?",
            (
                row["id"],
                row["state"],
                verdict,
                row["ended_at"] or row["started_at"] or _now(),
                _now(),
                issue_id,
            ),
        )

    async def _update_issue_columns(
        self, issue_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        assignments = ", ".join(f"{name} = ?" for name in updates)
        values = tuple(updates.values())
        with self.connect() as connection:
            current = connection.execute(
                "SELECT id FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
            if current is None:
                raise KeyError(f"Podium issue not found: {issue_id}")
            connection.execute(
                f"UPDATE issue SET {assignments}, updated_at = ? WHERE id = ?",
                (*values, _now(), issue_id),
            )
            connection.commit()
        return await self.get_issue(issue_id)

    async def consume_preferred_skill(
        self, issue_id: str, expected: str
    ) -> dict[str, Any]:
        """Compare-and-clear ``preferred_skill``.

        Nulls ``preferred_skill`` only when it still equals ``expected`` (the
        skill the scheduler consumed for this dispatch). If an operator changed
        the skill mid-window, the ``AND preferred_skill = ?`` guard no-ops so
        their newer pick survives to drive the next run.
        """
        with self.connect() as connection:
            connection.execute(
                "UPDATE issue SET preferred_skill = NULL, updated_at = ? "
                "WHERE id = ? AND preferred_skill = ?",
                (_now(), issue_id, expected),
            )
            connection.commit()
        return await self.get_issue(issue_id)

    async def _append_issue_field(
        self, issue_id: str, field_name: str, block: str
    ) -> dict[str, Any]:

        if field_name == "comments_md":
            return await self._append_comments(issue_id, block)
        if field_name == "context_md":
            return await self._append_context(issue_id, block)
        raise ValueError(f"unsupported issue field: {field_name}")

    async def _append_comments(self, issue_id: str, block: str) -> dict[str, Any]:
        with self.connect() as connection:
            current = connection.execute(
                "SELECT comments_md FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
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
            current = connection.execute(
                "SELECT context_md FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
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
    "agent_session_sha",
    "resumed",
)
_RUN_UPDATE_COLUMNS = tuple(key for key in _RUN_INSERT_COLUMNS if key != "issue_id")


def _infra_role_updates(
    labels: list[TrackerLabel | TrackerRole], *, adding: bool
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for label in labels:
        role = coerce_label_role(label)
        if role == TrackerRole.APPROVAL_REQUIRED:
            updates["approval_required"] = adding
        elif role == TrackerRole.APPROVED:
            updates["approved"] = adding
        elif role == TrackerRole.SCHEDULED:
            updates["scheduled_for"] = _now() if adding else None
    return updates


def _scheduled_due(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, datetime):
        scheduled_for = value
    else:
        try:
            scheduled_for = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=UTC)
    return scheduled_for.astimezone(UTC) <= datetime.now(UTC)


def _append_block(title: str, body: str) -> str:
    return f"{title}\n\n{body.strip()}".strip()


def _json_list(value: Any, item_type: type) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    items: list[Any] = []
    for item in parsed:
        with suppress(TypeError, ValueError):
            items.append(item_type(item))
    return items


def _now() -> str:
    return datetime.now(UTC).isoformat()
