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
