from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from web.api.schema import SCHEMA_SQL

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


def test_0021_adds_patrol_columns_and_backfills_dispatch_count(
    tmp_path: Path, monkeypatch
) -> None:
    """0021 adds patrol incident columns, agent_session_id, backfills
    dispatch_count from Run rows, and leaves operator defaults unchanged."""
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "web/api/migrations"))

    # ── Seed at 0020 with patrol + operator issues and runs ──────
    command.upgrade(config, "0020_patrol_issues_force_pi_duo")
    patrol_issue_ids: list[int] = []
    operator_issue_ids: list[int] = []
    with sqlite3.connect(db_path) as conn:
        # Patrol issues
        for _ in range(2):
            conn.execute(
                "INSERT INTO issue(binding_name, state, origin)"
                " VALUES ('homelab', 'todo', 'patrol')"
            )
            patrol_issue_ids.append(
                conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            )
        # One with external_id (legacy cutover case)
        conn.execute(
            "INSERT INTO issue(binding_name, state, origin, external_id)"
            " VALUES ('homelab', 'todo', 'patrol', 'homelab-patrol-infra-abc123')"
        )
        patrol_issue_ids.append(
            conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        # Operator issues — must remain at defaults
        for _ in range(2):
            conn.execute(
                "INSERT INTO issue(binding_name, state, origin)"
                " VALUES ('symphony', 'done', 'operator')"
            )
            operator_issue_ids.append(
                conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            )
        conn.commit()

        # Add runs for patrol issues: issue 0 = 4 runs, issue 1 = 1 run, issue 2 = 0 runs
        conn.executemany(
            "INSERT INTO run(issue_id, state) VALUES (?, 'succeeded')",
            [(patrol_issue_ids[0],)] * 4,
        )
        conn.execute(
            "INSERT INTO run(issue_id, state) VALUES (?, 'failed')",
            (patrol_issue_ids[1],),
        )
        # Operator issues also have runs (they must NOT be counted)
        conn.executemany(
            "INSERT INTO run(issue_id, state) VALUES (?, 'succeeded')",
            [(operator_issue_ids[0],), (operator_issue_ids[0],)],
        )
        conn.commit()

    # ── Upgrade to head (0021) ───────────────────────────────────
    command.upgrade(config, "head")

    with sqlite3.connect(db_path) as conn:
        # ── Verify all new columns exist on issue ────────────────
        columns = {row[1] for row in conn.execute("PRAGMA table_info(issue)")}
        expected_patrol = {
            "patrol_incident_family",
            "patrol_incident_resource",
            "patrol_first_seen_at",
            "patrol_last_seen_at",
            "patrol_occurrence_count",
            "patrol_current_severity",
            "patrol_last_dispatched_severity",
            "patrol_pending_severity",
            "patrol_consecutive_passes",
            "patrol_dispatch_count",
        }
        assert columns >= expected_patrol, f"Missing: {expected_patrol - columns}"

        # ── Verify agent_session_id on run ───────────────────────
        run_columns = {row[1] for row in conn.execute("PRAGMA table_info(run)")}
        assert "agent_session_id" in run_columns

        # ── Backfill: patrol_dispatch_count counts only own runs ─
        patrol_counts = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT id, patrol_dispatch_count FROM issue WHERE origin = 'patrol'"
            )
        }
        assert patrol_counts[patrol_issue_ids[0]] == 4, (
            f"issue 0: expected 4 got {patrol_counts[patrol_issue_ids[0]]}"
        )
        assert patrol_counts[patrol_issue_ids[1]] == 1, (
            f"issue 1: expected 1 got {patrol_counts[patrol_issue_ids[1]]}"
        )
        assert patrol_counts[patrol_issue_ids[2]] == 0, (
            f"issue 2 (external_id): expected 0 got {patrol_counts[patrol_issue_ids[2]]}"
        )

        # ── Operator issues keep default dispatch_count = 0 ──────
        operator_counts = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT id, patrol_dispatch_count FROM issue WHERE origin = 'operator'"
            )
        }
        assert all(cnt == 0 for cnt in operator_counts.values()), (
            f"operator counts: {operator_counts}"
        )

        # ── Operator patrol_severity columns default to NULL ──────
        operator_severities = conn.execute(
            "SELECT patrol_current_severity, patrol_last_dispatched_severity,"
            "  patrol_pending_severity FROM issue WHERE origin = 'operator'"
        ).fetchall()
        for row in operator_severities:
            assert all(v is None for v in row), f"operator non-null severity: {row}"

        # ── New patrol columns default to values, not errors ─────
        defaults = conn.execute(
            "SELECT patrol_occurrence_count, patrol_consecutive_passes FROM issue"
            " WHERE origin = 'patrol' LIMIT 1"
        ).fetchone()
        assert defaults == (0, 0), f"unexpected patrol defaults: {defaults}"

    # ── Runtime schema parity: fresh DB vs migrated DB ────────────
    fresh_path = tmp_path / "fresh.db"
    with sqlite3.connect(fresh_path) as fresh:
        fresh.executescript(SCHEMA_SQL)
    with sqlite3.connect(fresh_path) as fresh, sqlite3.connect(db_path) as migrated:
        fresh_tables = {
            r[0]
            for r in fresh.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        }
        migrated_tables = {
            r[0]
            for r in migrated.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        }
        assert fresh_tables == migrated_tables, (
            f"Fresh tables differ: extra={fresh_tables - migrated_tables},"
            f" missing={migrated_tables - fresh_tables}"
        )
        for table in fresh_tables:
            # PRAGMA does not support parameterised queries; table names come
            # from sqlite_schema so are safe for string interpolation.
            fresh_cols = {
                (r[1], r[2]) for r in fresh.execute(f'PRAGMA table_info("{table}")')
            }
            migrated_cols = {
                (r[1], r[2]) for r in migrated.execute(f'PRAGMA table_info("{table}")')
            }
            assert fresh_cols == migrated_cols, (
                f"{table} columns differ: fresh={fresh_cols} migrated={migrated_cols}"
            )
