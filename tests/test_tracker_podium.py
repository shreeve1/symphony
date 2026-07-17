from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest

import scheduler
from automation import LOOP_CAP_PREFIX, LOOP_COMPLETE_PREFIX, count_loop_iterations
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
    assert first["description"] == "Every 3600s"
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
