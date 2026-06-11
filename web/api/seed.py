from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

try:
    from .db import RUN_LOG_ROOT
except ImportError:  # pragma: no cover - supports uvicorn main:app from web/api
    RUN_LOG_ROOT = import_module("db").RUN_LOG_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
BINDINGS_PATH = REPO_ROOT / "bindings.yml"


def seed_if_empty(
    connection: sqlite3.Connection, bindings_path: Path = BINDINGS_PATH
) -> list[int]:
    binding_count = connection.execute("SELECT COUNT(*) FROM binding").fetchone()[0]
    if binding_count:
        return []

    seeded_run_ids: list[int] = []
    bindings = _load_bindings(bindings_path)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()

    for sort_order, binding in enumerate(bindings):
        name = str(binding["name"])
        base_branch = str(binding.get("base_branch") or "main")
        default_agent = str(binding.get("default_agent") or "pi")
        connection.execute(
            """
            INSERT INTO binding(name, display_name, color, sort_order, archived)
            VALUES (?, ?, '#888888', ?, FALSE)
            """,
            (name, name, sort_order),
        )

        for state in ("todo", "running"):
            cursor = connection.execute(
                """
                INSERT INTO issue(
                  binding_name, title, description, state, priority, preferred_agent,
                  reasoning_effort, worktree_active, base_branch, comments_md, context_md,
                  created_at, updated_at, last_event_at
                ) VALUES (?, ?, ?, ?, 'med', ?, 'high', FALSE, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    f"Seed {state.replace('_', ' ')} issue for {name}",
                    f"Tracer bullet seed issue for the {name} binding.",
                    state,
                    default_agent,
                    base_branch,
                    _seed_comments(name, state),
                    _seed_context(name, state),
                    now,
                    now,
                    now,
                ),
            )
            assert cursor.lastrowid is not None
            issue_id = cursor.lastrowid
            run_cursor = connection.execute(
                """
                INSERT INTO run(
                  issue_id, agent, provider, model, state, verdict, summary, exit_code,
                  cost_usd, input_tokens, output_tokens, worktree_path, branch_name,
                  base_branch, log_path, skill_invoked, started_at, ended_at
                ) VALUES (?, ?, 'seed', 'seed-model', 'succeeded', 'review', ?, 0,
                  0, 100, 50, NULL, NULL, ?, NULL, NULL, ?, ?)
                """,
                (
                    issue_id,
                    default_agent,
                    f"Seed run for {name} {state} issue.",
                    base_branch,
                    now,
                    now,
                ),
            )
            assert run_cursor.lastrowid is not None
            run_id = run_cursor.lastrowid
            seeded_run_ids.append(int(run_id))
            connection.execute(
                "UPDATE run SET log_path = ? WHERE id = ?",
                (str(RUN_LOG_ROOT / f"{run_id}.log"), run_id),
            )
            connection.execute(
                """
                UPDATE issue
                SET latest_run_id = ?, latest_verdict = 'review', latest_run_state = 'succeeded'
                WHERE id = ?
                """,
                (run_id, issue_id),
            )

    connection.commit()
    return seeded_run_ids


def _load_bindings(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    bindings = data.get("bindings") or []
    return [
        binding
        for binding in bindings
        if isinstance(binding, dict) and binding.get("name")
    ]


def _seed_comments(binding_name: str, state: str) -> str:
    return (
        f"# Operator comments\n\n"
        f"Seeded {state} issue for `{binding_name}`. Replace with real operator thread."
    )


def _seed_context(binding_name: str, state: str) -> str:
    return f"# Agent context\n\nSynthetic context for `{binding_name}` `{state}` issue."
