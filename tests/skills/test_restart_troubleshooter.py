from __future__ import annotations

from pathlib import Path

RESTART_PATH = Path(".claude/skills/symphony-restart/SKILL.md")
TROUBLESHOOTER_PATH = Path(".claude/skills/symphony-troubleshooter/SKILL.md")


def test_restart_skill_is_repo_local_and_keeps_approval_gate() -> None:
    text = RESTART_PATH.read_text(encoding="utf-8")

    assert "name: symphony-restart" in text
    assert "symphony-host.service" in text
    assert "explicit James approval" in text
    assert "symphony_started" in text
    assert "reconcile_startup_" in text
    assert "dispatch_completed" in text
    assert "/home/james/symphony-host.env" in text
    assert "Never read or print" in text


def test_troubleshooter_skill_is_podium_era_and_read_only() -> None:
    text = TROUBLESHOOTER_PATH.read_text(encoding="utf-8")

    assert "name: symphony-troubleshooter" in text
    assert "Podium" in text
    assert "GET /api/bindings" in text
    assert "GET /api/issues/{issue_id}/runs" in text
    assert "GET /api/runs/{run_id}" in text
    assert "/api/bindings/$NAME/issues" in text
    assert "sqlite3" in text
    assert "symphony-binding-scaffold" in text
    assert "symphony-binding-smoke" in text
    assert "symphony-workflow-author" in text
    assert "symphony-plane-recover" in text
    assert "read-only" in text.lower()
    assert "Never read or print" in text


def test_repo_local_operational_skills_do_not_keep_stale_plane_scaffold_language() -> (
    None
):
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in [RESTART_PATH, TROUBLESHOOTER_PATH]
    )

    assert "/home/james/plane" not in combined
    assert "symphony-project-scaffold" not in combined
    assert "Plane ticket" not in combined
    assert "Plane write" not in combined
    assert "api/v1/workspaces" not in combined
