from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest

import main
from agent_runner import AgentResult
from config import SymphonyConfig
from scheduler import run_tick
from web.api.schema import SCHEMA_SQL

PodiumTrackerAdapter = import_module("tracker_podium").PodiumTrackerAdapter


def _config(tmp_path: Path) -> SymphonyConfig:
    config = SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="podium-project",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        pi_provider="zai",
        pi_model="glm-5.1:high",
        run_timeout_ms=1000,
    )
    binding = replace(
        config.bindings[0],
        name="test",
        repo_path=tmp_path,
        binding_type="coding",
        tracker="podium",
    )
    return config.for_binding(binding)


def _seed_attachment(db_path: Path, repo_path: Path, issue_id: int, name: str) -> int:
    stored_name = f"stored-{name}"
    rel_path = f".symphony/attachments/{issue_id}/{stored_name}"
    path = repo_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name, encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO issue_attachment(
              issue_id, display_name, stored_name, content_type,
              size_bytes, storage_rel_path
            ) VALUES (?, ?, ?, 'text/plain', ?, ?)
            """,
            (issue_id, name, stored_name, len(name), rel_path),
        )
        connection.commit()
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def _seed_db(path: Path) -> int:
    skill_file = path.parent / "skills" / "dev-build" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("---\nname: dev-build\n---\nbuild it\n", encoding="utf-8")
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        connection.execute(
            "INSERT INTO skill(name, description, source) VALUES ('/dev-build', '', ?)",
            (str(skill_file),),
        )
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, preferred_model, reasoning_effort,
              comments_md, context_md, created_at, updated_at
            ) VALUES ('test', 'Dispatch me', 'Exercise Podium dispatch', 'todo', 'pi', '/dev-build', 'gpt-5.5', 'medium', '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_engine_dispatch_cycle_against_podium(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    (tmp_path / "WORKFLOW.md").write_text(
        "Repo policy. mode={{issue.mode}}", encoding="utf-8"
    )
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: podium dispatch ok\nfull output",
        )

    result = await run_tick(
        config,
        adapter,
        agent_runner=agent_runner,
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )
    issue = await adapter.get_issue(str(issue_id))

    assert result.dispatched is True
    assert result.issue_id == str(issue_id)
    assert issue["state"] == "in_review"
    assert "Symphony claimed at" not in issue["comments_md"]
    assert "podium dispatch ok" in issue["comments_md"]
    assert "full output" in issue["context_md"]
    # ADR-0011: coding bindings ignore WORKFLOW.md; the issue is the prompt.
    assert "Repo policy" not in prompts[0]
    assert "Dispatch me" in prompts[0]

    # [2.1]/[T.1.1] preferred_skill consumed on dispatch (ADR-0008).
    assert issue["preferred_skill"] is None
    # [T.1.3] standing config untouched by dispatch.
    assert issue["preferred_model"] == "gpt-5.5"
    assert issue["reasoning_effort"] == "medium"

    # [2.2]/[T.1.2] run.skill_invoked preserves the consumed skill.
    connection = sqlite3.connect(db_path)
    try:
        run_skill = connection.execute(
            "SELECT skill_invoked FROM run ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    assert run_skill is not None and run_skill[0] == "/dev-build"


@pytest.mark.asyncio
async def test_successful_run_consumes_only_dispatched_attachments(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    dispatched_id = _seed_attachment(db_path, tmp_path, issue_id, "first.txt")
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )
    uploaded_during_run: list[int] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        assert [attachment.id for attachment in issue.attachments] == [dispatched_id]
        uploaded_during_run.append(
            _seed_attachment(db_path, tmp_path, issue_id, "later.txt")
        )
        return AgentResult(0, 10, False, stdout="SYMPHONY_RESULT: done")

    result = await run_tick(
        config,
        adapter,
        agent_runner=agent_runner,
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )

    with sqlite3.connect(db_path) as connection:
        remaining = connection.execute(
            "SELECT id, stored_name FROM issue_attachment ORDER BY id"
        ).fetchall()
    assert result.dispatched is True
    assert remaining == [(uploaded_during_run[0], "stored-later.txt")]
    assert not (
        tmp_path / f".symphony/attachments/{issue_id}/stored-first.txt"
    ).exists()
    assert (tmp_path / f".symphony/attachments/{issue_id}/stored-later.txt").exists()


@pytest.mark.asyncio
async def test_cleanup_failure_retains_attachment_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scheduler import tick as scheduler_tick

    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    attachment_id = _seed_attachment(db_path, tmp_path, issue_id, "retry.txt")
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )

    def fail_delete(*args) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(scheduler_tick.attachment_store, "delete_local", fail_delete)
    result = await run_tick(
        config,
        adapter,
        agent_runner=lambda issue, prompt: AgentResult(
            0, 10, False, stdout="SYMPHONY_RESULT: done"
        ),
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM issue_attachment WHERE id = ?", (attachment_id,)
        ).fetchone()
    assert result.dispatched is True
    assert row == (attachment_id,)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["crash", "timeout", "nonzero"])
async def test_failed_run_retains_dispatched_attachments(
    tmp_path: Path,
    failure: str,
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    attachment_id = _seed_attachment(db_path, tmp_path, issue_id, "retry.txt")
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        if failure == "crash":
            raise RuntimeError("launch failed")
        if failure == "timeout":
            return AgentResult(0, 10, True)
        return AgentResult(2, 10, False)

    await run_tick(
        config,
        adapter,
        agent_runner=agent_runner,
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM issue_attachment WHERE id = ?", (attachment_id,)
        ).fetchone()
    assert row == (attachment_id,)
    assert (tmp_path / f".symphony/attachments/{issue_id}/stored-retry.txt").exists()


@pytest.mark.asyncio
async def test_gate_blocked_dispatch_preserves_preferred_skill(tmp_path: Path) -> None:
    # [2.3]/[T.2.1] A dispatch blocked by the gate (skill absent from catalog)
    # returns before _start_run_record, so preferred_skill is not consumed.
    db_path = tmp_path / "podium.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md, created_at, updated_at
            ) VALUES ('test', 'Block me', 'Skill missing from catalog', 'todo', 'pi', '/ghost-skill', '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        )
        connection.commit()
        issue_id = cursor.lastrowid
    finally:
        connection.close()
    assert issue_id is not None
    (tmp_path / "WORKFLOW.md").write_text("mode={{issue.mode}}", encoding="utf-8")
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        raise AssertionError("agent must not run for a gate-blocked dispatch")

    result = await run_tick(
        config,
        adapter,
        agent_runner=agent_runner,
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )
    issue = await adapter.get_issue(str(issue_id))

    assert result.dispatched is False
    assert issue["preferred_skill"] == "/ghost-skill"


@pytest.mark.asyncio
async def test_consume_preferred_skill_compare_and_clear(tmp_path: Path) -> None:
    # [2.5]/[T.2.3] W1 race guard: wrong expected no-ops; matching clears.
    db_path = tmp_path / "podium.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md, created_at, updated_at
            ) VALUES ('test', 'Race me', 'compare-and-clear', 'todo', 'pi', '/skill-A', '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        )
        connection.commit()
        issue_id = cursor.lastrowid
    finally:
        connection.close()
    assert issue_id is not None
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )

    # Operator re-picked: expected no longer matches → no-op, new pick survives.
    issue = await adapter.consume_preferred_skill(str(issue_id), "/skill-B")
    assert issue["preferred_skill"] == "/skill-A"

    # Matching expected → cleared.
    issue = await adapter.consume_preferred_skill(str(issue_id), "/skill-A")
    assert issue["preferred_skill"] is None


@pytest.mark.asyncio
async def test_podium_dispatch_injects_comments_once(tmp_path: Path) -> None:
    # Regression: the Podium renderer already embeds comments_md as the
    # "## Previous Issue Comments" block, so the scheduler must NOT append a
    # second copy on the Podium path (it would double the whole thread).
    db_path = tmp_path / "podium.db"
    marker = "UNIQUE_HISTORIC_COMMENT_MARKER"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_model, reasoning_effort, comments_md, context_md,
              created_at, updated_at
            ) VALUES ('test', 'Has history', 'Do work', 'todo', 'pi', 'gpt-5.5', 'medium', ?, '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """,
            (f"**Comment (2026-06-11):**\n{marker}",),
        )
        connection.commit()
        issue_id = cursor.lastrowid
    finally:
        connection.close()
    assert issue_id is not None
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        return AgentResult(0, 10, False, stdout="SYMPHONY_RESULT: done\nturn")

    await run_tick(
        config,
        adapter,
        agent_runner=agent_runner,
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )

    assert len(prompts) == 1
    assert prompts[0].count(marker) == 1
    assert prompts[0].count("## Previous Issue Comments") == 1
