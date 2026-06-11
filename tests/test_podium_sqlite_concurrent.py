from __future__ import annotations

import sqlite3
import threading
from importlib import import_module
from pathlib import Path

from web.api.schema import SCHEMA_SQL

PodiumTrackerAdapter = import_module("tracker_podium").PodiumTrackerAdapter


def _seed_db(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, comments_md, context_md,
              created_at, updated_at
            ) VALUES ('test', 'Concurrent', '', 'todo', '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid
    finally:
        connection.close()


def test_two_sqlite_writers_succeed_without_busy_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(value: str) -> None:
        adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="test")
        try:
            with adapter.connect() as connection:
                barrier.wait(timeout=5)
                connection.execute(
                    "UPDATE issue SET context_md = context_md || ? WHERE id = ?",
                    (value, issue_id),
                )
                connection.commit()
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(value,)) for value in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    with sqlite3.connect(db_path) as connection:
        context = connection.execute("SELECT context_md FROM issue WHERE id = ?", (issue_id,)).fetchone()[0]
    assert "A" in context
    assert "B" in context
