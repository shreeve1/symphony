"""Automation id AUTOINCREMENT + heal reused-id external_id collisions (issue #472)

A spawn automation fires its first issue but never re-fires: every scheduler
tick raises ``UNIQUE constraint failed: issue.external_id`` and the whole fire
batch rolls back, so ``occurrences_fired`` never advances (tracker_podium.py
``fire_due_spawn_automations``).

Root cause: ``automation.id`` was a bare ``INTEGER PRIMARY KEY``. SQLite reuses
a plain rowid after the row is deleted, and ``issue.external_id`` encodes the
automation id (``automation:<id>:<ordinal>`` for spawn, ``automation:<id>:loop``
for loop). When an operator deletes an automation and creates a new one, the new
row can reuse the deleted id; its first fire mints an external_id that already
belongs to an issue spawned by the deleted automation -> UNIQUE violation ->
rollback every tick, forever.

Fix (two parts):

1. Structural: rebuild ``automation`` with ``id INTEGER PRIMARY KEY
   AUTOINCREMENT``. AUTOINCREMENT tracks the high-water mark in
   ``sqlite_sequence`` and never reuses an id, so a recreated automation can
   never collide with a prior automation's issues again.

2. Heal live state: seed ``sqlite_sequence`` above the largest automation id
   *ever encoded in an issue.external_id* (not just the largest live automation
   id -- the colliding ids belong to deleted rows), then renumber any automation
   whose next mint target already exists as an issue onto a fresh id so the
   stuck rows fire cleanly on the next tick. ``automation`` has no inbound
   foreign keys, so renumbering ids is safe; historical issues keep their old
   external_ids.

Idempotent: skips the rebuild if the table already uses AUTOINCREMENT.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op


revision = "0024_automation_autoincrement_id"
down_revision = "0023_automation_pin_fields"
branch_labels = None
depends_on = None


_AUTOMATION_COLUMNS = (
    "id, binding_name, mode, enabled, template_title, template_body, "
    "spawn_interval_seconds, spawn_run_count, occurrences_fired, next_fire_at, "
    "loop_iteration_cap, loop_completion_marker, preferred_skill, "
    "preferred_agent, preferred_model, reasoning_effort, base_branch, "
    "worktree_active, created_at, updated_at"
)

_EXTERNAL_ID_RE = re.compile(r"^automation:(\d+):")


def _automation_sql() -> str:
    row = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'automation'"
        )
        .fetchone()
    )
    return str(row[0]) if row else ""


def _uses_autoincrement() -> bool:
    return "AUTOINCREMENT" in _automation_sql().upper()


def _rebuild_with_autoincrement() -> None:
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(
        """
        CREATE TABLE automation_new(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          binding_name TEXT NOT NULL REFERENCES binding(name) ON DELETE CASCADE,
          mode TEXT NOT NULL CHECK (mode IN ('spawn','loop')),
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          template_title TEXT NOT NULL,
          template_body TEXT NOT NULL,
          spawn_interval_seconds INTEGER,
          spawn_run_count INTEGER,
          occurrences_fired INTEGER NOT NULL DEFAULT 0,
          next_fire_at TIMESTAMP,
          loop_iteration_cap INTEGER,
          loop_completion_marker TEXT NOT NULL DEFAULT 'DONE.md',
          preferred_skill TEXT,
          preferred_agent TEXT,
          preferred_model TEXT,
          reasoning_effort TEXT DEFAULT 'high',
          base_branch TEXT,
          worktree_active BOOLEAN DEFAULT FALSE,
          created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute(
        f"INSERT INTO automation_new ({_AUTOMATION_COLUMNS})"
        f" SELECT {_AUTOMATION_COLUMNS} FROM automation"
    )
    op.execute("DROP TABLE automation")
    op.execute("ALTER TABLE automation_new RENAME TO automation")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_automation_binding_name"
        " ON automation(binding_name)"
    )
    op.execute("PRAGMA foreign_keys = ON")


def _max_id_in_external_ids(bind: sa.engine.Connection) -> int:
    highest = 0
    for (external_id,) in bind.exec_driver_sql(
        "SELECT external_id FROM issue WHERE external_id LIKE 'automation:%'"
    ).fetchall():
        match = _EXTERNAL_ID_RE.match(str(external_id))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def _existing_external_ids(bind: sa.engine.Connection) -> set[str]:
    return {
        str(row[0])
        for row in bind.exec_driver_sql(
            "SELECT external_id FROM issue WHERE external_id LIKE 'automation:%'"
        ).fetchall()
    }


def _next_spawn_mint_external_id(automation_id: int, occurrences: int) -> str:
    return f"automation:{automation_id}:{occurrences + 1}"


def _set_sequence(bind: sa.engine.Connection, value: int) -> None:
    # sqlite_sequence has no UNIQUE/PRIMARY KEY on name (it is an internal
    # SQLite bookkeeping table), so upsert via delete + insert. The row exists
    # only after the first AUTOINCREMENT insert into automation, hence the
    # rebuild's INSERT ... SELECT must have run before this is called.
    bind.exec_driver_sql("DELETE FROM sqlite_sequence WHERE name = 'automation'")
    bind.exec_driver_sql(
        "INSERT INTO sqlite_sequence(name, seq) VALUES ('automation', :seq)",
        {"seq": value},
    )


def _current_sequence(bind: sa.engine.Connection) -> int:
    row = bind.exec_driver_sql(
        "SELECT seq FROM sqlite_sequence WHERE name = 'automation'"
    ).fetchone()
    return int(row[0]) if row else 0


def _max_live_id(bind: sa.engine.Connection) -> int:
    row = bind.exec_driver_sql("SELECT COALESCE(MAX(id), 0) FROM automation").fetchone()
    return int(row[0]) if row else 0


def _heal_reused_id_collisions() -> None:
    bind = op.get_bind()
    live_max = _max_live_id(bind)
    # Never lower the sequence below its current value: an idempotent rerun with
    # deleted rows could otherwise seed below a previously allocated id and
    # re-permit reuse -- the exact hazard AUTOINCREMENT exists to prevent.
    high_water = max(live_max, _max_id_in_external_ids(bind), _current_sequence(bind))
    _set_sequence(bind, high_water)

    existing = _existing_external_ids(bind)
    # Only spawn automations get the UNIQUE-rollback bug: a spawn's next mint is
    # 'automation:<id>:<occurrences+1>', which exists already only when a reused
    # id inherited an orphan issue from a deleted automation. Loop automations
    # mint 'automation:<id>:loop' and their live loop issue is legitimately
    # theirs -- renumbering them would break the reconcile join
    # (tracker_podium.py) and duplicate the loop issue -- so leave loop rows.
    rows = bind.exec_driver_sql(
        "SELECT id, occurrences_fired FROM automation WHERE mode = 'spawn' ORDER BY id"
    ).fetchall()
    next_free = high_water
    for automation_id, occurrences in rows:
        target = _next_spawn_mint_external_id(int(automation_id), int(occurrences or 0))
        if target in existing:
            next_free += 1
            bind.exec_driver_sql(
                "UPDATE automation SET id = :new_id WHERE id = :old_id",
                {"new_id": next_free, "old_id": int(automation_id)},
            )
    _set_sequence(bind, next_free)


def upgrade() -> None:
    if not _uses_autoincrement():
        _rebuild_with_autoincrement()
    _heal_reused_id_collisions()


def downgrade() -> None:
    # Rebuild without AUTOINCREMENT. The heal (sequence seed + id renumber) is
    # not reversed: renumbered ids are already the durable identity of those
    # automations and reverting them would re-create the collision this
    # migration fixed. Idempotent so the chain does not fail.
    if not _uses_autoincrement():
        return
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(
        """
        CREATE TABLE automation_old(
          id INTEGER PRIMARY KEY,
          binding_name TEXT NOT NULL REFERENCES binding(name) ON DELETE CASCADE,
          mode TEXT NOT NULL CHECK (mode IN ('spawn','loop')),
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          template_title TEXT NOT NULL,
          template_body TEXT NOT NULL,
          spawn_interval_seconds INTEGER,
          spawn_run_count INTEGER,
          occurrences_fired INTEGER NOT NULL DEFAULT 0,
          next_fire_at TIMESTAMP,
          loop_iteration_cap INTEGER,
          loop_completion_marker TEXT NOT NULL DEFAULT 'DONE.md',
          preferred_skill TEXT,
          preferred_agent TEXT,
          preferred_model TEXT,
          reasoning_effort TEXT DEFAULT 'high',
          base_branch TEXT,
          worktree_active BOOLEAN DEFAULT FALSE,
          created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute(
        f"INSERT INTO automation_old ({_AUTOMATION_COLUMNS})"
        f" SELECT {_AUTOMATION_COLUMNS} FROM automation"
    )
    op.execute("DROP TABLE automation")
    op.execute("ALTER TABLE automation_old RENAME TO automation")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_automation_binding_name"
        " ON automation(binding_name)"
    )
    op.execute("PRAGMA foreign_keys = ON")
