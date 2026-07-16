from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_issue_dependency_columns_upgrade_and_downgrade(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "downgrade.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "web/api/migrations"))

    command.upgrade(config, "0009_issue_external_id")
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(issue)")}
        assert "blocked_by" not in columns
        assert "locks" not in columns

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(issue)")}
        assert {"blocked_by", "locks"} <= columns

    command.downgrade(config, "0009_issue_external_id")
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(issue)")}
        assert "blocked_by" not in columns
        assert "locks" not in columns


def test_0019_backfills_patrol_issues_to_flash(tmp_path: Path, monkeypatch) -> None:
    """0019 forces every patrol-origin issue onto flash (NULL or pinned v4-pro)
    while leaving operator issues' models untouched (issue #343)."""
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "web/api/migrations"))

    command.upgrade(config, "0018_run_cache_read_tokens")
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO issue(binding_name, state, origin, preferred_model)"
            " VALUES (?, 'todo', ?, ?)",
            [
                ("homelab", "patrol", None),  # legacy NULL -> v4-pro at dispatch
                ("homelab", "patrol", "deepseek-v4-pro"),  # explicitly pinned
                ("homelab", "patrol", "deepseek-v4-flash"),  # already correct
                ("homelab", "operator", "deepseek-v4-pro"),  # must NOT change
                ("homelab", "operator", None),  # must stay NULL
            ],
        )
        conn.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as conn:
        patrol = [
            row[0]
            for row in conn.execute(
                "SELECT preferred_model FROM issue WHERE origin = 'patrol'"
            )
        ]
        operator = sorted(
            (row[0] or "NULL")
            for row in conn.execute(
                "SELECT preferred_model FROM issue WHERE origin = 'operator'"
            )
        )
    assert patrol == ["deepseek-v4-flash"] * 3
    assert operator == ["NULL", "deepseek-v4-pro"]


def test_0020_backfills_patrol_issues_to_pi_duo(tmp_path: Path, monkeypatch) -> None:
    """0020 heals patrol-origin rows pinned to the bare provider string "pi-duo"
    (issue #413). C-0368 set PATROL_DEFAULT_MODEL = "pi-duo" — which
    resolve_model() cannot match against the catalog (id is "Duo"). The
    companion code fix flips the constant to "pi-duo/Duo"; this migration
    backfills the in-flight broken rows. Operator issues are untouched
    regardless of their preferred_model."""
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "web/api/migrations"))

    command.upgrade(config, "0019_patrol_issues_force_flash")
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO issue(binding_name, state, origin, preferred_model)"
            " VALUES (?, 'todo', ?, ?)",
            [
                ("homelab", "patrol", "pi-duo"),  # broken by C-0368 -> must heal
                ("homelab", "patrol", "pi-duo"),  # broken by C-0368 -> must heal
                ("homelab", "patrol", "deepseek-v4-flash"),  # legacy, must NOT change
                ("homelab", "patrol", "pi-duo/Duo"),  # already correct, must NOT change
                ("homelab", "operator", "pi-duo"),  # operator rows must NOT change
            ],
        )
        conn.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as conn:
        rows = list(
            conn.execute("SELECT origin, preferred_model FROM issue ORDER BY id")
        )
    by_origin: dict[str, list[str | None]] = {}
    for origin, model in rows:
        by_origin.setdefault(origin, []).append(model)
    assert by_origin["patrol"] == [
        "pi-duo/Duo",  # healed
        "pi-duo/Duo",  # healed
        "deepseek-v4-flash",  # untouched
        "pi-duo/Duo",  # untouched (already correct)
    ]
    assert by_origin["operator"] == ["pi-duo"]  # untouched
