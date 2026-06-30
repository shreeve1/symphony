from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import main
import scheduler
from agent_runner import AgentResult
from config import SymphonyConfig
from session_continuity import derive_session_id, session_file_path
from tracker_podium import PodiumTrackerAdapter
from web.api.schema import SCHEMA_SQL

# context_compaction.py is retired; the marker text is asserted-absent only, so
# keep a local literal rather than importing the deleted module.
COMPACTED_CONTEXT_MARKER = "SYMPHONY_COMPACTED_CONTEXT:"


def _config(tmp_path: Path) -> SymphonyConfig:
    config = SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="podium-project",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        pi_provider="openai-codex",
        pi_model="gpt-5.5",
        run_timeout_ms=1000,
    )
    binding = replace(
        config.bindings[0],
        name="trading",
        repo_path=tmp_path,
        binding_type="coding",
        tracker="podium",
        default_agent="pi",
    )
    return config.for_binding(binding)


def _seed_db(path: Path, *, preferred_agent: str = "pi") -> int:
    # The dispatch gate verifies the skill source exists on disk, so the
    # seeded row must point at a real SKILL.md.
    skill_file = path.parent / "skills" / "dev-build" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("---\nname: dev-build\n---\nbuild it\n", encoding="utf-8")
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        connection.execute(
            """
            INSERT INTO binding_settings(
              binding_name, context_compact_threshold_tokens,
              context_compact_keep_recent_runs
            ) VALUES ('trading', 1, 2)
            """
        )
        connection.execute(
            "INSERT INTO skill(name, description, source) VALUES ('/dev-build', '', ?)",
            (str(skill_file),),
        )
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, worktree_active, base_branch, comments_md,
              context_md, created_at, updated_at
            ) VALUES ('trading', 'Compact me', 'Exercise compaction', 'todo', ?, '/dev-build', 1, 'main', '', ?, '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """,
            (preferred_agent, "old run log\n" * 20),
        )
        connection.commit()
        assert cursor.lastrowid is not None
        (path.parent / "worktrees" / "trading" / str(cursor.lastrowid)).mkdir(
            parents=True, exist_ok=True
        )
        return cursor.lastrowid
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_dispatch_does_not_compact_oversized_context_before_operator_run(
    tmp_path: Path,
) -> None:
    # context compaction is retired: an oversized context_md no longer triggers
    # a pre-dispatch compaction agent call, and no extra Run row is created.
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    original_context = "old run log\n" * 20
    (tmp_path / "WORKFLOW.md").write_text(
        "Repo policy. mode={{issue.mode}}", encoding="utf-8"
    )
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        assert COMPACTED_CONTEXT_MARKER not in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: operator run ok",
            stderr="",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
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
    runs = [row for row in await adapter.list_issues() if row["id"] == str(issue_id)]
    with sqlite3.connect(db_path) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM run").fetchone()[0]

    assert result.dispatched is True
    assert issue["state"] == "in_review"
    # The original context_md survives verbatim as the prefix (the post-run
    # output append is the retained continuity path, not compaction), and the
    # context was never run through the compaction marker.
    assert issue["context_md"].startswith(original_context.rstrip())
    assert "<!-- context compacted on " not in issue["context_md"]
    # exactly one operator Run, and exactly one (operator) prompt render.
    assert run_count == 1
    assert len(prompts) == 1
    assert runs


@pytest.mark.asyncio
async def test_claude_dispatch_does_not_invoke_pi_compaction_before_claude(
    tmp_path: Path,
) -> None:
    # context compaction is retired: a Claude dispatch no longer routes through a
    # Pi compactor first. The compaction_agent_runner is dormant and never called.
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, preferred_agent="claude")
    (tmp_path / "WORKFLOW.md").write_text(
        "Repo policy. mode={{issue.mode}}", encoding="utf-8"
    )
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )
    pi_calls: list[tuple[str, str]] = []
    claude_calls: list[tuple[str, str]] = []

    def pi_compactor(issue, rendered_prompt: str) -> AgentResult:
        pi_calls.append((issue.resolved_provider, issue.resolved_model))
        return AgentResult(1, 1, False, stderr="pi compaction should not run")

    def claude_runner(issue, rendered_prompt: str) -> AgentResult:
        claude_calls.append((issue.resolved_provider, issue.resolved_model))
        assert COMPACTED_CONTEXT_MARKER not in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: claude dispatch ok",
            stderr="",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
        agent_runner=claude_runner,
        compaction_agent_runner=pi_compactor,
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
    run = await adapter.get_run(str(issue["latest_run_id"]))

    assert result.reason == "agent-marker-review"
    # the Pi compactor was never invoked; Claude ran exactly once.
    assert pi_calls == []
    assert claude_calls == [("", "claude-opus-4-8")]
    assert run is not None
    assert run["agent"] == "claude"
    assert run["provider"] == ""
    assert run["model"] == "claude-opus-4-8"


@pytest.mark.asyncio
async def test_pi_rpc_resume_uses_delta_prompt_skips_compaction_and_records_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    comments = """
### Older note
old context should not be re-fed

### Operator Reply (2026-06-13T00:00:00+00:00)
Please continue from the parked question.
""".strip()
    session_id = derive_session_id(str(issue_id))
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    (session_dir / f"2026-06-13_{session_id}.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    monkeypatch.setenv("PI_CODING_AGENT_SESSION_DIR", str(session_dir))
    with sqlite3.connect(db_path) as connection:
        previous = connection.execute(
            """
            INSERT INTO run(
              issue_id, agent, provider, model, state, verdict,
              started_at, ended_at, agent_session_sha, resumed
            ) VALUES (?, 'pi', 'openai-codex', 'gpt-5.5:high', 'succeeded',
                      'review', '2026-06-13T00:00:00+00:00',
                      '2026-06-13T00:01:00+00:00', 'unknown', 0)
            """,
            (issue_id,),
        ).lastrowid
        connection.execute(
            """
            UPDATE issue
            SET comments_md = ?, latest_run_id = ?, context_md = ?
            WHERE id = ?
            """,
            (comments, previous, "old run log\n" * 20, issue_id),
        )
        connection.commit()
    (tmp_path / "WORKFLOW.md").write_text(
        "Repo policy should be omitted on resume.", encoding="utf-8"
    )
    config = _config(tmp_path)
    rpc_binding = replace(config.bindings[0], pi_mode="rpc")
    config = config.for_binding(rpc_binding)
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=rpc_binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        assert issue.resumed is True
        assert issue.agent_session_sha == "unknown"
        assert "Please continue from the parked question." in rendered_prompt
        assert "old context should not be re-fed" not in rendered_prompt
        assert "old run log" not in rendered_prompt
        assert "Repo policy should be omitted" not in rendered_prompt
        assert COMPACTED_CONTEXT_MARKER not in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: resumed ok",
            stderr="",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
        agent_runner=agent_runner,
        render_prompt=lambda issue, *, resume=False: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
            resume=resume,
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 13, tzinfo=UTC),
        binding=rpc_binding,
    )
    with sqlite3.connect(db_path) as connection:
        run = connection.execute(
            "SELECT resumed, agent_session_sha FROM run ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert result.reason == "agent-marker-review"
    assert len(prompts) == 1
    assert run == (1, "unknown")


@pytest.mark.asyncio
async def test_claude_resume_uses_delta_prompt_skips_compaction_and_records_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, preferred_agent="claude")
    comments = """
### Older note
old context should not be re-fed

### Operator Reply (2026-06-13T00:00:00+00:00)
Please continue Claude from the parked question.
""".strip()
    session_id = derive_session_id(str(issue_id))
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    session_file = session_file_path(
        "claude", tmp_path / "worktrees" / "trading" / str(issue_id), session_id
    )
    session_file.parent.mkdir(parents=True)
    session_file.write_text("{}\n", encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        previous = connection.execute(
            """
            INSERT INTO run(
              issue_id, agent, provider, model, state, verdict,
              started_at, ended_at, agent_session_sha, resumed
            ) VALUES (?, 'claude', '', 'claude-opus-4-8', 'succeeded',
                      'review', '2026-06-13T00:00:00+00:00',
                      '2026-06-13T00:01:00+00:00', 'unknown', 0)
            """,
            (issue_id,),
        ).lastrowid
        connection.execute(
            """
            UPDATE issue
            SET comments_md = ?, latest_run_id = ?, context_md = ?
            WHERE id = ?
            """,
            (comments, previous, "old run log\n" * 20, issue_id),
        )
        connection.commit()
    (tmp_path / "WORKFLOW.md").write_text(
        "Repo policy should be omitted on Claude resume.", encoding="utf-8"
    )
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        assert issue.resumed is True
        assert issue.agent_session_sha == "unknown"
        assert "Please continue Claude from the parked question." in rendered_prompt
        assert "old context should not be re-fed" not in rendered_prompt
        assert "old run log" not in rendered_prompt
        assert "Repo policy should be omitted" not in rendered_prompt
        assert COMPACTED_CONTEXT_MARKER not in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: claude resumed ok",
            stderr="",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
        agent_runner=agent_runner,
        compaction_agent_runner=lambda issue, prompt: AgentResult(
            1, 1, False, stderr="compaction should not run"
        ),
        render_prompt=lambda issue, *, resume=False: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
            resume=resume,
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 13, tzinfo=UTC),
        binding=binding,
    )
    with sqlite3.connect(db_path) as connection:
        run = connection.execute(
            "SELECT resumed, agent_session_sha FROM run ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert result.reason == "agent-marker-review"
    assert len(prompts) == 1
    assert run == (1, "unknown")


@pytest.mark.asyncio
async def test_claude_resume_failure_falls_back_to_fresh_full_refeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path, preferred_agent="claude")
    comments = """
### Older note
old context should be re-fed on fallback

### Operator Reply (2026-06-13T00:00:00+00:00)
Please continue Claude from the parked question.
""".strip()
    session_id = derive_session_id(str(issue_id))
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    session_file = session_file_path(
        "claude", tmp_path / "worktrees" / "trading" / str(issue_id), session_id
    )
    session_file.parent.mkdir(parents=True)
    session_file.write_text("{}\n", encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        previous = connection.execute(
            """
            INSERT INTO run(
              issue_id, agent, provider, model, state, verdict,
              started_at, ended_at, agent_session_sha, resumed
            ) VALUES (?, 'claude', '', 'claude-opus-4-8', 'succeeded',
                      'review', '2026-06-13T00:00:00+00:00',
                      '2026-06-13T00:01:00+00:00', 'unknown', 0)
            """,
            (issue_id,),
        ).lastrowid
        connection.execute(
            """
            UPDATE issue
            SET comments_md = ?, latest_run_id = ?, context_md = ?
            WHERE id = ?
            """,
            (comments, previous, "short context", issue_id),
        )
        connection.execute(
            """
            UPDATE binding_settings
            SET context_compact_threshold_tokens = 1000
            WHERE binding_name = 'trading'
            """
        )
        connection.commit()
    (tmp_path / "WORKFLOW.md").write_text(
        "Repo policy should be present on fallback.", encoding="utf-8"
    )
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        if len(prompts) == 1:
            assert issue.resumed is True
            assert "old context should be re-fed" not in rendered_prompt
            raise RuntimeError("corrupt Claude session")
        assert issue.resumed is False
        assert "old context should be re-fed on fallback" in rendered_prompt
        # context_md is dormant: it is no longer injected into the fallback
        # prompt; only comments are re-fed.
        assert "short context" not in rendered_prompt
        # ADR-0011: coding bindings ignore WORKFLOW.md even on the fresh/
        # fallback refeed path; only comments are re-fed.
        assert "Repo policy should be present" not in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: claude fallback ok",
            stderr="",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
        agent_runner=agent_runner,
        render_prompt=lambda issue, *, resume=False: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
            resume=resume,
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 13, tzinfo=UTC),
        binding=binding,
    )
    with sqlite3.connect(db_path) as connection:
        runs = connection.execute(
            "SELECT state, summary, resumed FROM run ORDER BY id DESC LIMIT 2"
        ).fetchall()

    assert result.reason == "agent-marker-review"
    assert len(prompts) == 2
    assert runs[0] == ("succeeded", "claude fallback ok", 0)
    assert runs[1] == (
        "failed",
        "resume_failed: corrupt Claude session; fell_back=true",
        1,
    )


@pytest.mark.asyncio
async def test_resume_nonzero_falls_back_to_fresh_full_refeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    comments = """
### Older note
old context should be re-fed on fallback

### Operator Reply (2026-06-13T00:00:00+00:00)
Please continue from the parked question.
""".strip()
    session_id = derive_session_id(str(issue_id))
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    (session_dir / f"2026-06-13_{session_id}.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    monkeypatch.setenv("PI_CODING_AGENT_SESSION_DIR", str(session_dir))
    with sqlite3.connect(db_path) as connection:
        previous = connection.execute(
            """
            INSERT INTO run(
              issue_id, agent, provider, model, state, verdict,
              started_at, ended_at, agent_session_sha, resumed
            ) VALUES (?, 'pi', 'openai-codex', 'gpt-5.5:high', 'succeeded',
                      'review', '2026-06-13T00:00:00+00:00',
                      '2026-06-13T00:01:00+00:00', 'unknown', 0)
            """,
            (issue_id,),
        ).lastrowid
        connection.execute(
            """
            UPDATE issue
            SET comments_md = ?, latest_run_id = ?, context_md = ?
            WHERE id = ?
            """,
            (comments, previous, "short context", issue_id),
        )
        connection.execute(
            """
            UPDATE binding_settings
            SET context_compact_threshold_tokens = 1000
            WHERE binding_name = 'trading'
            """
        )
        connection.commit()
    config = _config(tmp_path)
    binding = replace(config.bindings[0], pi_mode="rpc")
    config = config.for_binding(binding)
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        if len(prompts) == 1:
            assert issue.resumed is True
            assert "old context should be re-fed" not in rendered_prompt
            return AgentResult(3, 10, False, stdout="", stderr="stale session")
        assert issue.resumed is False
        assert "old context should be re-fed on fallback" in rendered_prompt
        # context_md is dormant: no longer injected into the fallback prompt.
        assert "short context" not in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: pi fallback ok",
            stderr="",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
        agent_runner=agent_runner,
        render_prompt=lambda issue, *, resume=False: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
            resume=resume,
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 13, tzinfo=UTC),
        binding=binding,
    )
    with sqlite3.connect(db_path) as connection:
        runs = connection.execute(
            "SELECT state, summary, resumed FROM run ORDER BY id DESC LIMIT 2"
        ).fetchall()

    assert result.reason == "agent-marker-review"
    assert len(prompts) == 2
    assert runs[0] == ("succeeded", "pi fallback ok", 0)
    assert runs[1] == ("failed", "resume_failed: exit code 3; fell_back=true", 1)
