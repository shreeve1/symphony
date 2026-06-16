from __future__ import annotations

import json
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)
login = cast(Any, import_module("web.api.tests.conftest")).login


def _issue_by_title(db_path: Path, title: str) -> dict[str, Any]:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM issue WHERE title = ?", (title,)
        ).fetchone()
        return dict(row) if row else {}


def _restart_tailer() -> None:
    """Replace the module-level tailer with a fresh one so per-test state
    is clean (no stale cursors from previous tests)."""
    fresh = main._SessionTailer()
    main._session_tailer = fresh  # type: ignore[union-attr]


def test_tailer_reads_empty_session_file(monkeypatch, tmp_path: Path) -> None:
    """A session file that exists but is empty yields no tail lines."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    _restart_tailer()

    with TestClient(app) as client:
        login(client)
        issues = client.get("/api/bindings/symphony/issues").json()
        issue_id = issues[0]["id"]

        # Fake a running run to make the issue show up in the poll query
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'running', "
                "latest_run_state = 'running' WHERE id = ?",
                (issue_id,),
            )
            connection.execute(
                "UPDATE run SET state = 'running' WHERE issue_id = ?",
                (issue_id,),
            )
            connection.commit()

        # Ensure session-derived path does not exist
        # The tailer handles OSError gracefully

    poll_results: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        poll_results.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)

    # Run one poll cycle
    import asyncio

    asyncio.run(main._session_tailer._poll_running())

    # No publish call expected — the session file doesn't exist yet
    assert len(poll_results) == 0


def test_tailer_reads_new_lines(monkeypatch, tmp_path: Path) -> None:
    """A session file with content yields run.tail events with the full
    content on first detection."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    _restart_tailer()

    # Mock _repo_path_for_binding so the tailer can resolve cwd
    monkeypatch.setattr(
        main,
        "_repo_path_for_binding",
        lambda name: tmp_path / "binding-repo",
    )

    with TestClient(app) as client:
        login(client)
        issues = client.get("/api/bindings/symphony/issues").json()
        issue_id = issues[0]["id"]

        # Fake a running run with pi agent
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'running', "
                "latest_run_state = 'running' WHERE id = ?",
                (issue_id,),
            )
            connection.execute(
                "UPDATE run SET state = 'running', agent = 'pi' WHERE issue_id = ?",
                (issue_id,),
            )
            connection.commit()

    # Resolve the session file path
    from session_continuity import derive_session_id, session_file_path

    session_id = derive_session_id(issue_id)
    s_path = session_file_path("pi", tmp_path / "binding-repo", session_id)
    s_path.parent.mkdir(parents=True, exist_ok=True)
    s_path.write_text(
        json.dumps({"type": "turn", "content": "hello"})
        + "\n"
        + json.dumps({"type": "edit", "content": "world"})
        + "\n"
    )

    poll_results: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        poll_results.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)

    import asyncio

    asyncio.run(main._session_tailer._poll_running())

    assert len(poll_results) == 1
    msg = poll_results[0]
    assert msg["type"] == "run.tail"
    assert msg["issue_id"] == issue_id
    assert len(msg["lines"]) == 2
    assert "hello" in msg["lines"][0]
    assert "world" in msg["lines"][1]


def test_tailer_only_returns_new_lines_on_subsequent_polls(
    monkeypatch, tmp_path: Path
) -> None:
    """After the initial full read, subsequent polls return only appended
    lines."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    _restart_tailer()

    monkeypatch.setattr(
        main,
        "_repo_path_for_binding",
        lambda name: tmp_path / "binding-repo",
    )

    with TestClient(app) as client:
        login(client)
        issues = client.get("/api/bindings/symphony/issues").json()
        issue_id = issues[0]["id"]

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE issue SET state = 'running', "
                "latest_run_state = 'running' WHERE id = ?",
                (issue_id,),
            )
            connection.execute(
                "UPDATE run SET state = 'running', agent = 'pi' WHERE issue_id = ?",
                (issue_id,),
            )
            connection.commit()

    from session_continuity import derive_session_id, session_file_path

    session_id = derive_session_id(issue_id)
    s_path = session_file_path("pi", tmp_path / "binding-repo", session_id)
    s_path.parent.mkdir(parents=True, exist_ok=True)
    s_path.write_text(json.dumps({"type": "turn", "content": "hello"}) + "\n")

    poll_results: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        poll_results.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)

    import asyncio

    # First poll: reads existing content (1 line)
    asyncio.run(main._session_tailer._poll_running())
    assert len(poll_results) == 1
    assert len(poll_results[0]["lines"]) == 1

    # Second poll with no new data: no events
    asyncio.run(main._session_tailer._poll_running())
    assert len(poll_results) == 1  # no new event

    # Append more data
    with s_path.open("a") as f:
        f.write(json.dumps({"type": "edit", "content": "new line"}) + "\n")

    # Third poll: reads only the new line
    asyncio.run(main._session_tailer._poll_running())
    assert len(poll_results) == 2
    assert len(poll_results[1]["lines"]) == 1
    assert "new line" in poll_results[1]["lines"][0]
