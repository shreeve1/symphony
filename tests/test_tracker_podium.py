from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path

import pytest

import scheduler
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
            connection.execute("INSERT INTO skill(name, description, source) VALUES (?, '', 'test')", (preferred_skill,))
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
    assert not adapter.labels_contain_role(candidates[0].labels, TrackerRole.APPROVAL_REQUIRED)
    assert candidates[0].preferred_skill == "/dev-build"


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

    await adapter.add_comment(str(issue_id), CommentPayload(body="summary", outcome="done"))
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

    run = await adapter.record_run({"issue_id": issue_id, "agent": "pi", "state": "queued"})
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


def test_connections_enable_wal_and_busy_timeout(tmp_path: Path) -> None:
    adapter = PodiumTrackerAdapter(db_path=tmp_path / "podium.db", binding_name="test")

    with adapter.connect() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout == 5000
