from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest

import scheduler
from automation import (
    LOOP_BLOCKED_PREFIX,
    LOOP_CAP_PREFIX,
    LOOP_COMPLETE_PREFIX,
    LOOP_RETRY_PREFIX,
    count_loop_iterations,
    count_loop_retries,
    loop_retry_marker,
)
from plane_adapter import CommentPayload
from tracker_contract import PlaneLabel, TrackerRole
from web.api.schema import SCHEMA_SQL

TrackerAdapter = import_module("tracker_adapter").TrackerAdapter
PodiumTrackerAdapter = import_module("tracker_podium").PodiumTrackerAdapter


def _seed_db(
    path: Path, *, state: str = "todo", preferred_skill: str | None = "/dev-build"
) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        if preferred_skill is not None:
            connection.execute(
                "INSERT INTO skill(name, description, source) VALUES (?, '', 'test')",
                (preferred_skill,),
            )
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md, created_at, updated_at
            ) VALUES ('test', 'Podium issue', 'Do work', ?, 'pi', ?, '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """,
            (state, preferred_skill),
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid
    finally:
        connection.close()


def _seed_spawn_automation(
    path: Path,
    *,
    enabled: bool = True,
    mode: str = "spawn",
    run_count: int | None = None,
    occurrences: int = 0,
    next_fire_at: str | None = None,
    interval: int = 3600,
    loop_cap: int = 3,
    preferred_skill: str | None = None,
    preferred_agent: str | None = None,
    preferred_model: str | None = None,
    reasoning_effort: str | None = None,
    base_branch: str | None = None,
    worktree_active: bool = False,
) -> int:
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT OR IGNORE INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO automation(
              binding_name, mode, enabled, template_title, template_body,
              spawn_interval_seconds, spawn_run_count, occurrences_fired,
              next_fire_at, loop_iteration_cap,
              preferred_skill, preferred_agent, preferred_model,
              reasoning_effort, base_branch, worktree_active,
              created_at, updated_at
            ) VALUES ('test', ?, ?, 'Check {binding}', 'Every {interval}s',
                      ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?,
                      '2026-07-17T00:00:00+00:00',
                      '2026-07-17T00:00:00+00:00')
            """,
            (
                mode,
                enabled,
                interval,
                run_count,
                occurrences,
                next_fire_at,
                loop_cap if mode == "loop" else None,
                preferred_skill,
                preferred_agent,
                preferred_model,
                reasoning_effort,
                base_branch,
                worktree_active,
            ),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid


@pytest.mark.asyncio
async def test_podium_adapter_satisfies_runtime_protocol(tmp_path: Path) -> None:
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    assert isinstance(adapter, TrackerAdapter)


@pytest.mark.asyncio
async def test_list_issues_candidates_and_state_helpers(tmp_path: Path) -> None:
    issue_id = _seed_db(tmp_path / "podium.db")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    issues = await adapter.list_issues(TrackerRole.STATE_TODO)
    candidates = await adapter.list_candidates()

    assert issues[0]["id"] == str(issue_id)
    assert adapter.issue_is_state(issues[0], TrackerRole.STATE_TODO)
    assert adapter.issue_labels(issues[0]) == ("build", "agent:pi")
    assert adapter.labels_contain_role(candidates[0].labels, TrackerRole.MODE_BUILD)
    assert not adapter.labels_contain_role(
        candidates[0].labels, TrackerRole.APPROVAL_REQUIRED
    )
    assert candidates[0].preferred_skill == "/dev-build"


@pytest.mark.asyncio
async def test_candidate_attachment_id_supports_exact_row_consumption(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    with sqlite3.connect(db_path) as connection:
        first = connection.execute(
            """
            INSERT INTO issue_attachment(
              issue_id, display_name, stored_name, content_type,
              size_bytes, storage_rel_path
            ) VALUES (?, 'first.txt', 'first-stored.txt', 'text/plain', 5, ?)
            """,
            (issue_id, f".symphony/attachments/{issue_id}/first-stored.txt"),
        )
        second = connection.execute(
            """
            INSERT INTO issue_attachment(
              issue_id, display_name, stored_name, content_type,
              size_bytes, storage_rel_path
            ) VALUES (?, 'later.txt', 'later-stored.txt', 'text/plain', 5, ?)
            """,
            (issue_id, f".symphony/attachments/{issue_id}/later-stored.txt"),
        )
        connection.commit()
    assert first.lastrowid is not None
    assert second.lastrowid is not None
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    attachment = (await adapter.list_candidates())[0].attachments[0]
    consumed = await adapter.consume_attachment(
        str(issue_id), attachment.id, attachment.stored_name
    )

    with sqlite3.connect(db_path) as connection:
        remaining = connection.execute(
            "SELECT id FROM issue_attachment ORDER BY id"
        ).fetchall()
    assert attachment.id == first.lastrowid
    assert consumed is True
    assert remaining == [(second.lastrowid,)]
    assert (
        await adapter.consume_attachment(
            str(issue_id), second.lastrowid, "reused-id-with-new-name.txt"
        )
        is False
    )
    assert (
        await adapter.consume_attachment("999", second.lastrowid, "later-stored.txt")
        is False
    )


@pytest.mark.asyncio
async def test_hold_excludes_todo_issue_from_candidates_until_cleared(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    # A held todo issue is never emitted as a dispatch candidate.
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE issue SET hold = 1 WHERE id = ?", (issue_id,))
        connection.commit()
    assert await adapter.list_candidates() == []

    # Clearing hold releases it on the next poll.
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE issue SET hold = 0 WHERE id = ?", (issue_id,))
        connection.commit()
    candidates = await adapter.list_candidates()
    assert len(candidates) == 1
    assert candidates[0].id == str(issue_id)


@pytest.mark.asyncio
async def test_get_issue_transition_and_label_noops(tmp_path: Path) -> None:
    issue_id = _seed_db(tmp_path / "podium.db")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    issue = await adapter.get_issue(str(issue_id))
    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_RUNNING)
    labeled = await adapter.add_label(str(issue_id), PlaneLabel.PLAN)
    unlabeled = await adapter.remove_label(str(issue_id), PlaneLabel.PLAN)
    many_labeled = await adapter.add_labels(str(issue_id), [PlaneLabel.BUILD])
    many_unlabeled = await adapter.remove_labels(str(issue_id), [PlaneLabel.BUILD])

    assert issue["state"] == "todo"
    assert updated["state"] == "running"
    assert labeled["state"] == "running"
    assert unlabeled["state"] == "running"
    assert many_labeled["state"] == "running"
    assert many_unlabeled["state"] == "running"


@pytest.mark.asyncio
async def test_transition_state_does_not_resurrect_archived_issue(
    tmp_path: Path,
) -> None:
    issue_id = _seed_db(tmp_path / "podium.db", state="archived")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)
    issue = await adapter.get_issue(str(issue_id))

    assert updated["state"] == "archived"
    assert issue["state"] == "archived"


@pytest.mark.asyncio
async def test_transition_state_to_inbox_state_clears_dismissal(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, state="todo")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET inbox_dismissed_at = ? WHERE id = ?",
            ("2026-06-11T00:00:00+00:00", issue_id),
        )
        connection.commit()
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_IN_REVIEW)

    assert updated["state"] == "in_review"
    assert updated["inbox_dismissed_at"] is None


@pytest.mark.asyncio
async def test_transition_state_to_non_inbox_state_keeps_dismissal(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, state="blocked")
    dismissed = "2026-06-11T00:00:00+00:00"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET inbox_dismissed_at = ? WHERE id = ?",
            (dismissed, issue_id),
        )
        connection.commit()
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_RUNNING)

    assert updated["state"] == "running"
    assert updated["inbox_dismissed_at"] == dismissed


@pytest.mark.asyncio
async def test_comments_context_and_comment_listing(tmp_path: Path) -> None:
    issue_id = _seed_db(tmp_path / "podium.db")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    await adapter.add_comment(
        str(issue_id), CommentPayload(body="summary", outcome="done")
    )
    await adapter.post_comment(str(issue_id), "second summary")
    await adapter.append_context(str(issue_id), "full output blob")
    comments = await adapter.list_comments(str(issue_id))
    issue = await adapter.get_issue(str(issue_id))

    assert "### Symphony AI Summary" not in issue["comments_md"]
    assert "**Outcome:** done" in issue["comments_md"]
    assert "second summary" in comments[0]["body"]
    assert "### Symphony Context Append" in issue["context_md"]
    assert "full output blob" in issue["context_md"]


@pytest.mark.asyncio
async def test_claimed_at_reads_run_record_started_at(tmp_path: Path) -> None:
    # With the claim comment removed, _claimed_at must source claim time from
    # the latest Run record's started_at (no comment fallback needed).
    issue_id = _seed_db(tmp_path / "podium.db", state="running")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    run = await adapter.record_run(
        {"issue_id": issue_id, "agent": "pi", "state": "queued"}
    )
    await adapter.update_run(
        run["id"], {"state": "running", "started_at": "2026-06-11T01:02:03+00:00"}
    )

    claimed = await scheduler._claimed_at(adapter, str(issue_id))
    assert claimed is not None
    assert claimed.isoformat() == "2026-06-11T01:02:03+00:00"


@pytest.mark.asyncio
async def test_run_roundtrip(tmp_path: Path) -> None:
    issue_id = _seed_db(tmp_path / "podium.db")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    run = await adapter.record_run(
        {
            "issue_id": issue_id,
            "agent": "pi",
            "provider": "zai",
            "model": "glm-5.1:high",
            "state": "succeeded",
            "verdict": "review",
            "summary": "ok",
            "exit_code": 0,
            "started_at": "2026-06-11T00:00:00+00:00",
            "ended_at": "2026-06-11T00:00:01+00:00",
        }
    )
    fetched = await adapter.get_run(str(run["id"]))
    issue = await adapter.get_issue(str(issue_id))

    assert fetched is not None
    assert fetched["summary"] == "ok"
    assert issue["latest_run_id"] == run["id"]
    assert issue["latest_run_state"] == "succeeded"


@pytest.mark.asyncio
async def test_run_retry_verdict_roundtrip_leaves_latest_verdict_empty(
    tmp_path: Path,
) -> None:
    issue_id = _seed_db(tmp_path / "podium.db")
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    run = await adapter.record_run(
        {
            "issue_id": issue_id,
            "agent": "pi",
            "state": "failed",
            "verdict": "retry",
            "summary": "transient",
            "exit_code": 1,
        }
    )
    issue = await adapter.get_issue(str(issue_id))

    assert run["verdict"] == "retry"
    assert issue["latest_run_id"] == run["id"]
    assert issue["latest_run_state"] == "failed"
    assert issue["latest_verdict"] is None


@pytest.mark.asyncio
async def test_issue_dependency_fields_parse_json_lists(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET blocked_by = ?, locks = ? WHERE id = ?",
            ('[1, "2", "bad"]', '["schema", 3]', issue_id),
        )
        connection.commit()
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    issue = await adapter.get_issue(str(issue_id))

    assert issue["blocked_by"] == [1, 2]
    assert issue["locks"] == ["schema", "3"]


@pytest.mark.asyncio
async def test_issue_dependency_fields_default_to_empty_lists(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    issue = await adapter.get_issue(str(issue_id))

    assert issue["auto_land"] is False
    assert issue["blocked_by"] == []
    assert issue["locks"] == []

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET blocked_by = ?, locks = ? WHERE id = ?",
            ("not-json", '{"not": "a list"}', issue_id),
        )
        connection.commit()

    issue = await adapter.get_issue(str(issue_id))
    assert issue["auto_land"] is False
    assert issue["blocked_by"] == []
    assert issue["locks"] == []


@pytest.mark.asyncio
async def test_reland_pending_reselects_marked_review_issue(tmp_path: Path) -> None:
    from redispatch_core import RELAND_DONE_PREFIX, RELAND_PENDING_PREFIX

    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, state="in_review")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET comments_md = ?, auto_land = 1 WHERE id = ?",
            (f"### Symphony Review (1)\n\n{RELAND_PENDING_PREFIX} · one", issue_id),
        )
        connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md, created_at, updated_at
            ) VALUES ('test', 'balanced', '', 'in_review', 'pi', '/dev-build', ?, '',
                      '2026-06-11T00:00:00+00:00',
                      '2026-06-11T00:00:00+00:00')
            """,
            (
                f"### Symphony Review (1)\n\n{RELAND_PENDING_PREFIX} · one\n{RELAND_DONE_PREFIX} · one",
            ),
        )
        connection.commit()

    candidates = await PodiumTrackerAdapter(
        db_path=db_path, binding_name="test"
    ).list_candidates()

    assert [candidate.id for candidate in candidates] == [str(issue_id)]
    assert candidates[0].review_dispatch is True


@pytest.mark.asyncio
async def test_non_auto_land_in_review_issue_is_not_review_dispatched(
    tmp_path: Path,
) -> None:
    """Operator-authored (auto_land=false) issues skip the review run entirely
    — they stay in_review for a manual merge (issue #149)."""
    db_path = tmp_path / "podium.db"
    _seed_db(db_path, state="in_review")

    candidates = await PodiumTrackerAdapter(
        db_path=db_path, binding_name="test"
    ).list_candidates()

    assert candidates == []


def test_connections_enable_wal_and_busy_timeout(tmp_path: Path) -> None:
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    with adapter.connect() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout == 5000


@pytest.mark.asyncio
async def test_operator_reland_marker_does_not_reselect_as_review_run(
    tmp_path: Path,
) -> None:
    """An in_review issue whose only reland marker is the OPERATOR variant is
    NOT re-selected as a review run — the distinct prefix keeps
    list_candidates' review reselection off it (finding #3)."""
    from redispatch_core import OPERATOR_RELAND_PENDING_PREFIX

    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, state="in_review")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET comments_md = ? WHERE id = ?",
            (
                f"### Symphony Review (1)\n\n{OPERATOR_RELAND_PENDING_PREFIX} · one",
                issue_id,
            ),
        )
        connection.commit()

    candidates = await PodiumTrackerAdapter(
        db_path=db_path, binding_name="test"
    ).list_candidates()

    # The operator marker is not a review reland: no review reselection.
    assert candidates == []


# ---------------------------------------------------------------------------
# Patrol-specific tests
# ---------------------------------------------------------------------------


def _patrol_db(
    path: Path,
    *,
    dispatch_count: int = 0,
    last_severity: str | None = None,
    state: str = "todo",
) -> int:
    """Seed a single patrol issue with optional dispatch state."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, origin,
              preferred_agent, comments_md, context_md,
              patrol_dispatch_count, patrol_current_severity,
              patrol_last_dispatched_severity,
              created_at, updated_at
            ) VALUES (
              'test', 'Patrol issue', 'A patrol finding', ?, 'patrol',
              'pi', '', '',
              ?, 'critical',
              ?,
              '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00'
            )
            """,
            (state, dispatch_count, last_severity),
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_patrol_record_run_increments_dispatch_count(tmp_path: Path) -> None:
    """record_run increments patrol_dispatch_count for patrol issues."""
    db_path = tmp_path / "podium.db"
    issue_id = _patrol_db(db_path, dispatch_count=2, last_severity="medium")
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    run = await adapter.record_run(
        {
            "issue_id": issue_id,
            "agent": "pi",
            "state": "queued",
            "agent_session_id": "test-session-id",
        }
    )
    issue = await adapter.get_issue(str(issue_id))

    assert issue["patrol_dispatch_count"] == 3
    assert issue["patrol_last_dispatched_severity"] == "critical"
    assert issue["patrol_pending_severity"] is None
    assert run["agent_session_id"] == "test-session-id"


@pytest.mark.asyncio
async def test_patrol_record_run_non_patrol_unchanged(tmp_path: Path) -> None:
    """record_run does not touch patrol columns for non-patrol issues."""
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    run = await adapter.record_run(
        {
            "issue_id": issue_id,
            "agent": "pi",
            "state": "queued",
            "agent_session_id": None,
        }
    )
    issue = await adapter.get_issue(str(issue_id))

    assert issue["origin"] == "operator"
    assert run["agent_session_id"] is None


@pytest.mark.asyncio
async def test_patrol_terminal_triggers_pruning(tmp_path: Path) -> None:
    """update_run triggers patrol pruning when a run becomes terminal."""
    import sqlite3

    db_path = tmp_path / "podium.db"
    issue_id = _patrol_db(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    # Create 5 runs
    run_ids = []
    for i in range(5):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO run(issue_id, state, verdict, started_at, cost_usd, log_path)
                VALUES (?, 'succeeded', 'done', ?, 0, ?)
                """,
                (
                    issue_id,
                    f"2026-06-11T00:0{i}:00+00:00",
                    str(tmp_path / f"log-{i}.log"),
                ),
            )
            conn.commit()
        with sqlite3.connect(db_path) as conn:
            r = conn.execute(
                "SELECT MAX(id) as id FROM run WHERE issue_id = ?", (issue_id,)
            ).fetchone()
            run_ids.append(int(r[0]))
    # Set latest_run_id to the oldest run so projection repair is tested
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE issue SET latest_run_id = ? WHERE id = ?",
            (run_ids[0], issue_id),
        )
        conn.commit()

    # Call prune_patrol_runs directly (terminal-triggered pruning in
    # update_run calls the same internal helper)
    counts = await adapter.prune_patrol_runs()

    assert counts["pruned_rows"] == 2
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        remaining = conn.execute(
            "SELECT id, state FROM run WHERE issue_id = ? ORDER BY id",
            (issue_id,),
        ).fetchall()
    assert len(remaining) == 3
    # latest_run_id should point to the newest surviving run
    issue = await adapter.get_issue(str(issue_id))
    assert int(issue["latest_run_id"]) == run_ids[-1]


@pytest.mark.asyncio
async def test_patrol_pruning_skips_non_patrol_via_update_run(tmp_path: Path) -> None:
    """Wave 5 regression: update_run's terminal trigger must NOT prune non-patrol rows.

    Before the fix, _prune_patrol_runs_for_issue was called from update_run
    without an origin gate, so a 5+ run operator/coding issue would silently
    lose completed rows to the patrol-3-row cap. T.4.4 invariant.
    """
    import sqlite3

    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)  # operator issue
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    # Seed 5 completed runs on the operator issue.
    run_ids: list[int] = []
    for i in range(5):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """INSERT INTO run(issue_id, state, verdict, started_at, cost_usd)
                   VALUES (?, 'running', NULL, ?, 0)""",
                (issue_id, f"2026-06-11T00:0{i}:00+00:00"),
            )
            conn.commit()
        with sqlite3.connect(db_path) as conn:
            r = conn.execute(
                "SELECT MAX(id) AS id FROM run WHERE issue_id = ?", (issue_id,)
            ).fetchone()
            run_ids.append(int(r[0]))

    # Transition the newest running run to terminal via update_run — this
    # is the path that previously invoked patrol pruning without an origin
    # gate.
    await adapter.update_run(
        str(run_ids[-1]), {"state": "succeeded", "verdict": "done"}
    )

    # All 5 rows must remain. T.4.4 invariant: non-patrol runs follow the
    # existing 90-day/100-log policy, never the patrol 3-row cap.
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM run WHERE issue_id = ?", (issue_id,)
        ).fetchone()[0]
    assert count == 5, (
        f"non-patrol pruning regression: {count} runs remain (expected 5)"
    )


@pytest.mark.asyncio
async def test_spawn_automation_mints_independent_issues_and_advances(tmp_path: Path):
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    noon = datetime(2026, 7, 17, 12, tzinfo=UTC)

    assert (
        await adapter.fire_due_spawn_automations(now=noon, base_branch="develop") == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        first = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert first["title"] == "Check test"
    # Issue #10 / ADR-0041: worktree-off spawns append a base-branch commit
    # directive so the agent knows to commit to base (clean checkout =
    # completion signal). The user template precedes the directive.
    assert first["description"].startswith("Every 3600s\n\n")
    assert "Symphony worktree-off spawn" in first["description"]
    assert "**Base branch:** `develop`" in first["description"]
    assert first["base_branch"] == "develop"
    assert first["external_id"] == f"automation:{automation_id}:1"
    assert [candidate.id for candidate in await adapter.list_candidates()] == [
        str(first["id"])
    ]

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'blocked' WHERE id = ?", (first["id"],)
        )
    assert (
        await adapter.fire_due_spawn_automations(
            now=datetime(2026, 7, 17, 13, tzinfo=UTC), base_branch="develop"
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        automation = dict(connection.execute("SELECT * FROM automation").fetchone())
        issues = connection.execute("SELECT * FROM issue ORDER BY id").fetchall()
    assert automation["occurrences_fired"] == 2
    assert automation["enabled"] == 1
    assert [row["external_id"] for row in issues] == [
        f"automation:{automation_id}:1",
        f"automation:{automation_id}:2",
    ]


@pytest.mark.asyncio
async def test_spawn_automation_finite_count_and_filters(tmp_path: Path):
    db_path = tmp_path / "podium.db"
    final_id = _seed_spawn_automation(db_path, run_count=2, occurrences=1)
    exhausted_id = _seed_spawn_automation(db_path, run_count=2, occurrences=2)
    future_id = _seed_spawn_automation(
        db_path, next_fire_at="2026-07-17T14:00:00+00:00"
    )
    disabled_id = _seed_spawn_automation(db_path, enabled=False)
    loop_id = _seed_spawn_automation(db_path, mode="loop")
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    assert (
        await adapter.fire_due_spawn_automations(
            now=datetime(2026, 7, 17, 12, tzinfo=UTC), base_branch="main"
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        rows = {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                "SELECT id, enabled, occurrences_fired FROM automation"
            )
        }
        external_ids = [
            row[0] for row in connection.execute("SELECT external_id FROM issue")
        ]
    assert rows[final_id] == (0, 2)
    assert rows[exhausted_id] == (0, 2)
    assert rows[future_id] == (1, 0)
    assert rows[disabled_id] == (0, 0)
    assert rows[loop_id] == (1, 0)
    assert external_ids == [f"automation:{final_id}:2"]


@pytest.mark.asyncio
async def test_spawn_automation_threads_pin_fields_and_origin_automation(
    tmp_path: Path,
) -> None:
    """Issue #459: per-automation pin fields propagate to the spawned Issue row,
    origin='automation' is written (Q2), and base_branch falls back to the
    binding default when NULL on the automation (Q3).
    """
    db_path = tmp_path / "podium.db"
    _seed_spawn_automation(
        db_path,
        preferred_skill="homelab-operations",
        preferred_agent="pi",
        preferred_model="pi-duo/Duo",
        reasoning_effort="xhigh",
        worktree_active=True,
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    noon = datetime(2026, 7, 17, 12, tzinfo=UTC)

    assert (
        await adapter.fire_due_spawn_automations(now=noon, base_branch="develop") == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert row["preferred_skill"] == "homelab-operations"
    assert row["preferred_agent"] == "pi"
    assert row["preferred_model"] == "pi-duo/Duo"
    assert row["reasoning_effort"] == "xhigh"
    assert row["base_branch"] == "develop"  # from binding default, automation is NULL
    assert bool(row["worktree_active"]) is True
    assert row["origin"] == "automation"


@pytest.mark.asyncio
async def test_spawn_automation_worktree_on_sets_auto_land_true_off_false(
    tmp_path: Path,
) -> None:
    """Issue #9 / ADR-0041: worktree-ON spawn Issues are created with
    auto_land=True so the existing ADR-0023 auto-land pipeline runs review
    and merges the worktree branch to base (uniform terminal behavior —
    spawn self-completes to done). Worktree-OFF stays auto_land=False; the
    separate base-checkout land path is #10.
    """
    db_on = tmp_path / "on.db"
    _seed_spawn_automation(db_on, worktree_active=True)
    on_adapter = PodiumTrackerAdapter(db_path=db_on, binding_name="test")
    noon = datetime(2026, 7, 17, 12, tzinfo=UTC)
    assert (
        await on_adapter.fire_due_spawn_automations(now=noon, base_branch="main") == 1
    )
    with sqlite3.connect(db_on) as connection:
        connection.row_factory = sqlite3.Row
        on_row = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert bool(on_row["worktree_active"]) is True
    assert bool(on_row["auto_land"]) is True

    db_off = tmp_path / "off.db"
    _seed_spawn_automation(db_off, worktree_active=False)
    off_adapter = PodiumTrackerAdapter(db_path=db_off, binding_name="test")
    assert (
        await off_adapter.fire_due_spawn_automations(now=noon, base_branch="main") == 1
    )
    with sqlite3.connect(db_off) as connection:
        connection.row_factory = sqlite3.Row
        off_row = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert bool(off_row["worktree_active"]) is False
    assert bool(off_row["auto_land"]) is False  # land path for worktree-off is #10


@pytest.mark.asyncio
async def test_spawn_automation_worktree_off_appends_base_commit_directive(
    tmp_path: Path,
) -> None:
    """Issue #10 / ADR-0041: worktree-off spawns append a base-branch commit
    directive to the description so the agent knows to commit to the base
    checkout (clean + committed = completion signal). Worktree-ON spawns
    skip the directive: their worktree-merge land path doesn't require the
    agent to commit to base.
    """
    db_off = tmp_path / "off.db"
    _seed_spawn_automation(db_off, worktree_active=False)
    off_adapter = PodiumTrackerAdapter(db_path=db_off, binding_name="test")
    noon = datetime(2026, 7, 17, 12, tzinfo=UTC)
    assert (
        await off_adapter.fire_due_spawn_automations(now=noon, base_branch="main") == 1
    )
    with sqlite3.connect(db_off) as connection:
        connection.row_factory = sqlite3.Row
        off_row = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert "Symphony worktree-off spawn" in off_row["description"]
    assert "**Base branch:** `main`" in off_row["description"]
    # Original template body must precede the directive.
    assert off_row["description"].startswith("Every 3600s\n\n")

    db_on = tmp_path / "on.db"
    _seed_spawn_automation(db_on, worktree_active=True)
    on_adapter = PodiumTrackerAdapter(db_path=db_on, binding_name="test")
    assert (
        await on_adapter.fire_due_spawn_automations(now=noon, base_branch="main") == 1
    )
    with sqlite3.connect(db_on) as connection:
        connection.row_factory = sqlite3.Row
        on_row = dict(connection.execute("SELECT * FROM issue").fetchone())
    # Worktree-on spawns must NOT receive the directive — they land via the
    # ADR-0023 worktree-merge pipeline, not the base-checkout land path.
    assert "Symphony worktree-off spawn" not in on_row["description"]
    assert on_row["description"] == "Every 3600s"


async def test_spawn_automation_base_branch_override_wins_over_binding_default(
    tmp_path: Path,
) -> None:
    """Issue #459 (Q3): a non-NULL base_branch on the automation row wins over
    the binding default supplied by the fire path."""
    db_path = tmp_path / "podium.db"
    _seed_spawn_automation(db_path, base_branch="feature/x")
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    await adapter.fire_due_spawn_automations(
        now=datetime(2026, 7, 17, 12, tzinfo=UTC), base_branch="develop"
    )
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT base_branch FROM issue").fetchone()
    assert row[0] == "feature/x"


@pytest.mark.asyncio
async def test_loop_automation_threads_pin_fields_and_force_worktree(
    tmp_path: Path,
) -> None:
    """Issue #459: loop automations propagate pin fields too, and
    worktree_active is forced True at fire-time regardless of the automation
    column (operator-confirmed 2026-07-17: "loops use worktrees").
    """
    db_path = tmp_path / "podium.db"
    _seed_spawn_automation(
        db_path,
        mode="loop",
        loop_cap=5,
        preferred_skill="diagnose",
        preferred_model="deepseek-v4-flash",
        reasoning_effort="low",
        worktree_active=False,  # loop forces True at fire-time
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    await adapter.reconcile_loop_automations(
        now=datetime(2026, 7, 17, 12, tzinfo=UTC),
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert row["preferred_skill"] == "diagnose"
    assert row["preferred_model"] == "deepseek-v4-flash"
    assert row["reasoning_effort"] == "low"
    assert row["base_branch"] == "main"
    assert bool(row["worktree_active"]) is True  # forced True, automation said False
    assert row["origin"] == "automation"


@pytest.mark.asyncio
async def test_loop_automation_redispatches_one_issue_then_parks_at_cap(tmp_path: Path):
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=2)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="develop",
            completion_marker_exists=lambda issue_id, marker: False,
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert issue["external_id"] == f"automation:{automation_id}:loop"
    assert issue["worktree_active"] == 1
    assert issue["auto_land"] == 0
    assert issue["base_branch"] == "develop"
    assert "## Symphony Loop" in issue["description"]
    assert count_loop_iterations(issue["comments_md"]) == 1
    candidate = (await adapter.list_candidates())[0]
    assert candidate.fresh_context is True

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE automation SET enabled = 0 WHERE id = ?", (automation_id,)
        )
    assert await adapter.list_candidates() == []
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE automation SET enabled = 1 WHERE id = ?", (automation_id,)
        )
    assert (await adapter.list_candidates())[0].fresh_context is True
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'in_review' WHERE id = ?", (issue["id"],)
        )
    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="develop",
            completion_marker_exists=lambda issue_id, marker: False,
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        redispatched = dict(
            connection.execute(
                "SELECT * FROM issue WHERE id = ?", (issue["id"],)
            ).fetchone()
        )
        assert connection.execute("SELECT COUNT(*) FROM issue").fetchone()[0] == 1
    assert redispatched["state"] == "todo"
    assert count_loop_iterations(redispatched["comments_md"]) == 2

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'in_review' WHERE id = ?", (issue["id"],)
        )
    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="develop",
            completion_marker_exists=lambda issue_id, marker: False,
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        parked = dict(connection.execute("SELECT * FROM issue").fetchone())
        automation = dict(
            connection.execute(
                "SELECT * FROM automation WHERE id = ?", (automation_id,)
            ).fetchone()
        )
    assert parked["state"] == "in_review"
    assert LOOP_CAP_PREFIX in parked["comments_md"]
    assert automation["enabled"] == 0


@pytest.mark.asyncio
async def test_loop_automation_done_marker_parks_in_review(tmp_path: Path):
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop")
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]
        connection.execute(
            "UPDATE issue SET state = 'in_review' WHERE id = ?", (issue_id,)
        )

    seen: list[tuple[str, str]] = []
    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: (
                seen.append((issue_id, marker)) or True
            ),
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    assert seen == [(str(issue_id), "DONE.md")]
    assert issue["state"] == "in_review"
    assert LOOP_COMPLETE_PREFIX in issue["comments_md"]
    assert enabled == 0

    # A later operator/ADR-0014 redispatch is not another loop iteration and
    # must recover normal session continuity.
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE issue SET state = 'todo' WHERE id = ?", (issue_id,))
    candidate = (await adapter.list_candidates())[0]
    assert candidate.fresh_context is False


@pytest.mark.asyncio
async def test_spawn_automation_batch_rolls_back_on_invalid_interval(tmp_path: Path):
    db_path = tmp_path / "podium.db"
    valid_id = _seed_spawn_automation(db_path)
    invalid_id = _seed_spawn_automation(db_path, interval=0)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    with pytest.raises(ValueError, match="must be positive"):
        await adapter.fire_due_spawn_automations(
            now=datetime(2026, 7, 17, 12, tzinfo=UTC), base_branch="main"
        )
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM issue").fetchone()[0] == 0
        rows = dict(
            connection.execute(
                "SELECT id, occurrences_fired FROM automation WHERE id IN (?, ?)",
                (valid_id, invalid_id),
            )
        )
    assert rows == {valid_id: 0, invalid_id: 0}


# ---------------------------------------------------------------------------
# Issue #8 — Loop failure retry (ADR-0041)
# A blocked loop Issue is re-dispatched up to 3 consecutive times; on the 3rd
# consecutive block the loop terminates with `### Symphony Loop Blocked` and
# the automation is disabled. A recovered iteration (state → in_review) resets
# the failure count; retry budget is independent of the iteration cap.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_automation_blocked_issue_is_redispatched_with_retry_marker(
    tmp_path: Path,
) -> None:
    """First blocked iteration re-dispatches and appends ### Symphony Loop Retry."""
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=10)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    # First reconcile creates the loop Issue with iteration 1.
    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]
        connection.execute(
            "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
        )

    # Blocked → re-dispatch with retry marker.
    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
    assert issue["state"] == "todo"
    assert LOOP_RETRY_PREFIX in issue["comments_md"]
    assert count_loop_retries(issue["comments_md"]) == 1
    # Retry markers must NOT consume the iteration cap.
    assert count_loop_iterations(issue["comments_md"]) == 1
    # Automation stays enabled — the loop is still being retried.
    with sqlite3.connect(db_path) as connection:
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    assert enabled == 1


@pytest.mark.asyncio
async def test_loop_automation_third_consecutive_block_terminates_with_disabled(
    tmp_path: Path,
) -> None:
    """3rd consecutive block appends ### Symphony Loop Blocked and disables automation."""
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=10)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]

    # Three consecutive blocked iterations.
    for _ in range(3):
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
            )
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    # The 3rd strike appends the terminal block marker.
    assert LOOP_BLOCKED_PREFIX in issue["comments_md"]
    # Retry markers in the comments trail: 2 (1st and 2nd strike) + block
    # marker on the 3rd. The function returns the count of retry markers
    # since the last productive iteration; the 3rd strike appends the block
    # marker (not another retry), so this is 2.
    assert count_loop_retries(issue["comments_md"]) == 2
    # The Issue is left inspectable (worktree preserved) — NOT parked in_review.
    assert issue["state"] == "blocked"
    # Automation is disabled so it doesn't auto re-arm.
    assert enabled == 0


@pytest.mark.asyncio
async def test_loop_automation_success_resets_failure_count(tmp_path: Path) -> None:
    """An iteration that reaches in_review resets the consecutive failure count."""
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=10)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]

    # Two blocked iterations accumulate 2 retry markers.
    for _ in range(2):
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
            )
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        comments = dict(
            connection.execute(
                "SELECT comments_md FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
        )["comments_md"]
    assert count_loop_retries(comments) == 2

    # Now succeed: iteration completes and the agent parks the Issue in_review.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'in_review' WHERE id = ?", (issue_id,)
        )
    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )

    # A fresh failure after recovery should be treated as the FIRST consecutive
    # failure, not the third — so the loop must be re-dispatched (not terminated).
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
        )
    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    # After recovery, the next block is treated as the 1st consecutive failure:
    # retry marker appended, state back to todo, automation still enabled.
    assert issue["state"] == "todo"
    assert LOOP_RETRY_PREFIX in issue["comments_md"]
    # Total retry markers = 2 prior + 1 new = 3 markers in comments,
    # but only the most-recent consecutive run matters for the cap.
    # Recovery (iteration marker after the failures) resets the consecutive
    # count to zero, so the 1 new retry after the recovered iteration is the
    # only one counted from the new consecutive run.
    assert count_loop_retries(issue["comments_md"]) == 1
    assert enabled == 1


@pytest.mark.asyncio
async def test_loop_automation_retry_budget_independent_of_iteration_cap(
    tmp_path: Path,
) -> None:
    """Retry budget (3) does not consume the iteration cap (separate counters)."""
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=2)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]

    # Two blocked iterations → 2 retry markers, automation still enabled.
    for _ in range(2):
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
            )
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    # Iteration count is still 1 — retries did not advance iteration count.
    assert count_loop_iterations(issue["comments_md"]) == 1
    assert count_loop_retries(issue["comments_md"]) == 2
    # Loop has not yet hit either cap — neither iteration cap nor retry cap.
    assert enabled == 1
    # The Issue is back in the dispatch queue.
    assert issue["state"] == "todo"


@pytest.mark.asyncio
async def test_loop_automation_blocked_before_iteration_cap_takes_retry_path(
    tmp_path: Path,
) -> None:
    """Failure-vs-cap precedence: a blocked iteration that has NOT yet
    exceeded the iteration cap is re-dispatched via the retry path even when
    the automation's cap is small. The retry budget (3) is independent of the
    iteration cap, so a cap of 1 must not consume the retry budget.
    """
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=1)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]

    # The first iteration blocks. The iteration cap (1) is not yet exceeded
    # by a productive in_review iteration, so the retry path must fire:
    # state goes blocked → todo, retry marker appended, automation stays
    # enabled. No cap marker must be appended yet — the cap is reached only
    # when an iteration lands in_review, not when one is blocked.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
        )
    assert (
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )
        == 1
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = dict(connection.execute("SELECT * FROM issue").fetchone())
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    assert issue["state"] == "todo"
    assert LOOP_RETRY_PREFIX in issue["comments_md"]
    assert LOOP_CAP_PREFIX not in issue["comments_md"]
    assert enabled == 1


@pytest.mark.asyncio
async def test_loop_automation_blocked_terminal_is_idempotent(tmp_path: Path) -> None:
    """Once an Issue carries the LOOP_BLOCKED_PREFIX terminal marker, a second
    reconciler tick must not append another marker or re-count failures; it
    only ensures the automation is disabled and stops there.
    """
    db_path = tmp_path / "podium.db"
    automation_id = _seed_spawn_automation(db_path, mode="loop", loop_cap=10)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        issue_id = connection.execute("SELECT id FROM issue").fetchone()[0]

    # Three consecutive blocked iterations → terminates with block marker.
    for _ in range(3):
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'blocked' WHERE id = ?", (issue_id,)
            )
        await adapter.reconcile_loop_automations(
            now=now,
            base_branch="main",
            completion_marker_exists=lambda issue_id, marker: False,
        )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        first = dict(connection.execute("SELECT * FROM issue").fetchone())
        first_comments_len = len(first["comments_md"] or "")
        first_marker_count = (first["comments_md"] or "").count(LOOP_BLOCKED_PREFIX)

    # A second reconciler tick on the same terminated Issue must be a no-op
    # for comments: no new block marker, no length growth, automation stays 0.
    await adapter.reconcile_loop_automations(
        now=now,
        base_branch="main",
        completion_marker_exists=lambda issue_id, marker: False,
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        second = dict(connection.execute("SELECT * FROM issue").fetchone())
        enabled = connection.execute(
            "SELECT enabled FROM automation WHERE id = ?", (automation_id,)
        ).fetchone()[0]
    assert len(second["comments_md"] or "") == first_comments_len
    assert (second["comments_md"] or "").count(
        LOOP_BLOCKED_PREFIX
    ) == first_marker_count
    assert enabled == 0


@pytest.mark.asyncio
async def test_loop_automation_retry_marker_helper_renders_expected_text(
    tmp_path: Path,
) -> None:
    """Pure helper test: the marker is timestamped and follows the existing
    Symphony Loop marker convention."""
    from datetime import UTC

    body = loop_retry_marker(datetime(2026, 7, 17, 12, tzinfo=UTC))
    assert body.startswith(LOOP_RETRY_PREFIX)
    assert "2026-07-17" in body


# --- ADR-0042 section-2 GitHub close-back (issue #515) -------------------


def _seed_github_issue(
    path: Path,
    *,
    external_id: str = "github:shreeve1/symphony#515",
    worktree_path: str | None = None,
    sha: str = "abc1234",
) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md,
              external_id, created_at, updated_at
            ) VALUES ('test', 'Podium issue', 'Do work', 'running', 'pi',
                      '/dev-build', '', '', ?, '2026-06-11T00:00:00+00:00',
                      '2026-06-11T00:00:00+00:00')
            """,
            (external_id,),
        )
        issue_id = cursor.lastrowid
        assert issue_id is not None
        if sha:
            connection.execute(
                """
                INSERT INTO run(
                  issue_id, agent, state, verdict, started_at, ended_at,
                  agent_session_sha, worktree_path
                ) VALUES (?, 'pi', 'succeeded', 'done', ?, ?, ?, ?)
                """,
                (
                    issue_id,
                    "2026-06-11T00:00:00+00:00",
                    "2026-06-11T00:01:00+00:00",
                    sha,
                    worktree_path or "",
                ),
            )
        connection.commit()
        return issue_id
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_github_close_back_fires_on_done_with_landed_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "515"
    worktree.mkdir(parents=True)
    issue_id = _seed_github_issue(db_path, worktree_path=str(worktree))

    calls: list[tuple[str, str, str, str, str]] = []

    def fake_run_gh_close(
        issue_id_arg: str, github_number: str, owner: str, repo_name: str, sha: str
    ) -> None:
        calls.append((issue_id_arg, github_number, owner, repo_name, sha))

    monkeypatch.setattr("tracker_podium._run_gh_close", fake_run_gh_close)
    monkeypatch.setattr(
        "tracker_podium.resolve_github_repo", lambda _path: ("shreeve1", "symphony")
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "done"
    assert calls == [(str(issue_id), "515", "shreeve1", "symphony", "abc1234")]


@pytest.mark.asyncio
async def test_github_close_back_skipped_for_non_github_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    # Same shape as the GitHub seed, but the external_id is a non-github
    # placeholder (e.g. automation-only). No gh call must fire.
    issue_id = _seed_github_issue(db_path, external_id="automation:1:1")

    calls: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        "tracker_podium._run_gh_close",
        lambda *args, **kwargs: calls.append(args[:4]) or None,
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "done"
    assert calls == []


@pytest.mark.asyncio
async def test_github_close_back_fires_exactly_once_across_terminal_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All four STATE_DONE call sites funnel through transition_state; verify
    that re-calling it (e.g. review-terminal, spawn-worktree-off, verified-close,
    operator-reland — one of which calls it twice is fine) closes once per
    real land and never for a non-done transition."""
    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "42"
    worktree.mkdir(parents=True)
    issue_id = _seed_github_issue(
        db_path,
        external_id="github:owner/repo#42",
        worktree_path=str(worktree),
        sha="deadbeef",
    )

    calls: list[str] = []
    monkeypatch.setattr(
        "tracker_podium._run_gh_close",
        lambda *args, **kwargs: calls.append(args[1]) or None,
    )
    monkeypatch.setattr(
        "tracker_podium.resolve_github_repo", lambda _path: ("owner", "repo")
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    # Non-done transitions never trigger the close-back.
    await adapter.transition_state(str(issue_id), TrackerRole.STATE_RUNNING)
    await adapter.transition_state(str(issue_id), TrackerRole.STATE_IN_REVIEW)
    await adapter.transition_state(str(issue_id), TrackerRole.STATE_BLOCKED)
    assert calls == []

    # One done transition closes exactly once.
    await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)
    assert calls == ["42"]

    # A repeated STATE_DONE is a no-op for the close-back (already done;
    # would otherwise re-comment on GitHub).
    await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)
    assert calls == ["42"]


@pytest.mark.asyncio
async def test_github_close_back_no_op_when_no_succeeded_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "7"
    worktree.mkdir(parents=True)
    # No sha = no successful land; close-back must skip (no fake sha in comment).
    issue_id = _seed_github_issue(
        db_path,
        external_id="github:owner/repo#7",
        worktree_path=str(worktree),
        sha="",
    )

    calls: list[str] = []
    monkeypatch.setattr(
        "tracker_podium._run_gh_close",
        lambda *args, **kwargs: calls.append("fired") or None,
    )
    monkeypatch.setattr(
        "tracker_podium.resolve_github_repo", lambda _path: ("owner", "repo")
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "done"
    assert calls == []


@pytest.mark.asyncio
async def test_github_close_back_no_op_for_non_github_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    # Repo whose remote is not GitHub — resolve_github_repo returns None.
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "9"
    worktree.mkdir(parents=True)
    issue_id = _seed_github_issue(
        db_path,
        external_id="github:owner/repo#9",
        worktree_path=str(worktree),
    )

    calls: list[str] = []
    monkeypatch.setattr(
        "tracker_podium._run_gh_close",
        lambda *args, **kwargs: calls.append("fired") or None,
    )
    monkeypatch.setattr("tracker_podium.resolve_github_repo", lambda _path: None)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "done"
    assert calls == []


@pytest.mark.asyncio
async def test_github_close_back_fail_soft_on_subprocess_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "11"
    worktree.mkdir(parents=True)
    issue_id = _seed_github_issue(
        db_path,
        external_id="github:owner/repo#11",
        worktree_path=str(worktree),
    )

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("gh exploded")

    monkeypatch.setattr("tracker_podium._run_gh_close", explode)
    monkeypatch.setattr(
        "tracker_podium.resolve_github_repo", lambda _path: ("owner", "repo")
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    # The done transition must still succeed even when gh fails.
    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "done"
    log_text = "\n".join(record.message for record in caplog.records)
    assert "github_close_back_failed" in log_text


@pytest.mark.asyncio
async def test_github_close_back_skipped_for_archived_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "8"
    worktree.mkdir(parents=True)
    issue_id = _seed_github_issue(
        db_path,
        external_id="github:owner/repo#8",
        worktree_path=str(worktree),
    )
    # Force the issue into the archived terminal bucket the UPDATE skips.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE issue SET state = 'archived' WHERE id = ?", (issue_id,)
        )
        connection.commit()

    calls: list[str] = []
    monkeypatch.setattr(
        "tracker_podium._run_gh_close",
        lambda *args, **kwargs: calls.append("fired") or None,
    )
    monkeypatch.setattr(
        "tracker_podium.resolve_github_repo", lambda _path: ("owner", "repo")
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "archived"
    assert calls == []


@pytest.mark.asyncio
async def test_parse_github_number_helper() -> None:
    from tracker_podium import _parse_github_number

    assert _parse_github_number("github:owner/repo#515") == "515"
    assert _parse_github_number("github:a/b/c#7") == "7"
    assert _parse_github_number("automation:1:1") is None
    assert _parse_github_number("github:no-number") is None
    assert _parse_github_number("") is None


@pytest.mark.asyncio
async def test_run_gh_close_builds_command_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Pure helper test: the command shape matches ADR-0042 section 2."""
    from tracker_podium import _run_gh_close

    captured: dict[str, object] = {}

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _Result()

    monkeypatch.setattr("tracker_podium.subprocess.run", fake_run)
    caplog.set_level("INFO", logger="tracker_podium")

    _run_gh_close("1", "515", "shreeve1", "symphony", "abc1234")

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:5] == ["gh", "issue", "close", "515", "--repo"]
    assert cmd[5] == "shreeve1/symphony"
    assert cmd[6] == "--comment"
    assert cmd[7] == "Landed in abc1234."
    log_text = "\n".join(record.message for record in caplog.records)
    assert "github_close_back_ok" in log_text
    assert "sha=abc1234" in log_text


def test_run_gh_close_tolerates_already_closed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Already-closed GitHub issue exits non-zero but is not a failure
    (ADR-0042 consequences: close-back must tolerate an already-closed issue)."""
    from tracker_podium import _run_gh_close

    class _Result:
        returncode = 1
        stderr = "HTTP 422: Issue is already closed"

    monkeypatch.setattr(
        "tracker_podium.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )
    caplog.set_level("INFO", logger="tracker_podium")

    # Must not raise. The Podium done-transition path calls this via
    # asyncio.to_thread; the wrapper itself is sync.
    _run_gh_close("1", "515", "shreeve1", "symphony", "abc1234")

    log_text = "\n".join(record.message for record in caplog.records)
    assert "github_close_back_already_closed" in log_text
    # Explicitly NOT a failure log — already-closed is a tolerated no-op,
    # not a problem to alert on.
    assert "github_close_back_failed" not in log_text


@pytest.mark.asyncio
async def test_done_transition_completes_when_gh_says_already_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The done transition must still land when gh reports already closed.

    Full-stack view of the same guarantee: no error bubbles up out of
    transition_state, and the issue still ends up in `done`."""

    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    worktree = repo / "worktrees" / "test" / "12"
    worktree.mkdir(parents=True)
    issue_id = _seed_github_issue(
        db_path,
        external_id="github:owner/repo#12",
        worktree_path=str(worktree),
    )

    class _Result:
        returncode = 1
        stderr = "GraphQL: Could not resolve to a node (Issue is already closed)"

    monkeypatch.setattr(
        "tracker_podium.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )
    monkeypatch.setattr(
        "tracker_podium.resolve_github_repo", lambda _path: ("owner", "repo")
    )
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")

    with caplog.at_level("INFO", logger="tracker_podium"):
        updated = await adapter.transition_state(str(issue_id), TrackerRole.STATE_DONE)

    assert updated["state"] == "done"
    log_text = "\n".join(record.message for record in caplog.records)
    assert "github_close_back_already_closed" in log_text
    assert "github_close_back_failed" not in log_text
