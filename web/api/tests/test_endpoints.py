from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

login = cast(Any, import_module("web.api.tests.conftest")).login

main = import_module("web.api.main")
app = cast(Any, main.app)


def test_read_endpoints_seed_temp_db(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        login(client)
        bindings_response = client.get("/api/bindings")
        assert bindings_response.status_code == 200
        bindings = bindings_response.json()
        binding_names = {binding["name"] for binding in bindings}
        assert {"homelab", "symphony"}.issubset(binding_names)
        assert all(binding["pi_mode"] in {"one-shot", "rpc"} for binding in bindings)
        assert all(
            binding["binding_type"] in {"infra", "coding"} for binding in bindings
        )
        assert all("claude_persist" in binding for binding in bindings)
        assert all(isinstance(binding["claude_persist"], bool) for binding in bindings)

        symphony_issues_response = client.get("/api/bindings/symphony/issues")
        assert symphony_issues_response.status_code == 200
        symphony_issues = symphony_issues_response.json()
        assert len(symphony_issues) >= 2
        assert all("latest_verdict" in issue for issue in symphony_issues)
        assert all("latest_run_state" in issue for issue in symphony_issues)
        assert all(issue["binding_type"] == "coding" for issue in symphony_issues)
        assert all(issue["approval_required"] is False for issue in symphony_issues)
        assert all(issue["approved"] is False for issue in symphony_issues)
        assert all(issue["scheduled_for"] is None for issue in symphony_issues)

        homelab_issues_response = client.get("/api/bindings/homelab/issues")
        assert homelab_issues_response.status_code == 200
        homelab_issues = homelab_issues_response.json()
        assert all(issue["binding_type"] == "infra" for issue in homelab_issues)

        issue_id = symphony_issues[0]["id"]
        issue_response = client.get(f"/api/issues/{issue_id}")
        assert issue_response.status_code == 200
        issue = issue_response.json()
        assert issue["comments_md"]
        assert issue["context_md"]

        runs_response = client.get(f"/api/issues/{issue_id}/runs")
        assert runs_response.status_code == 200
        runs = runs_response.json()
        assert len(runs) >= 1
        assert runs[0]["state"] == "succeeded"
        assert runs[0]["verdict"] == "review"

    with sqlite3.connect(db_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    assert revision == main.INITIAL_REVISION

    env = {**os.environ, "PODIUM_DB_PATH": str(db_path)}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
    )


def test_skills_endpoint_returns_rows_sorted_by_name(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        login(client)
        with main.connect(db_path) as connection:
            connection.executemany(
                "INSERT INTO skill(name, description, source) VALUES (?, ?, ?)",
                [
                    ("zulu", "Zulu skill", "/tmp/zulu/SKILL.md"),
                    ("alpha", "Alpha skill", "/tmp/alpha/SKILL.md"),
                ],
            )
            connection.commit()

        response = client.get("/api/skills")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "alpha",
            "description": "Alpha skill",
            "source": "/tmp/alpha/SKILL.md",
        },
        {"name": "zulu", "description": "Zulu skill", "source": "/tmp/zulu/SKILL.md"},
    ]


def test_bindings_endpoint_surfaces_remote_repo_name(
    monkeypatch, tmp_path: Path
) -> None:
    # Issue 34: a remote binding's card/sidebar label should read "name — repo".
    # The API enriches /api/bindings with is_remote + repo_name from bindings.yml.
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    from web.api.tests.conftest import REMOTE_BINDING_ENTRY, REMOTE_BINDING_NAME

    with TestClient(app) as client:
        login(client)
        with main.connect(db_path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO binding(name, display_name, sort_order) VALUES (?, ?, 99)",
                (REMOTE_BINDING_NAME, REMOTE_BINDING_NAME),
            )
            connection.commit()
        monkeypatch.setattr(main, "_bindings_override", [REMOTE_BINDING_ENTRY])
        monkeypatch.setattr(
            main,
            "_binding_claude_persist_for",
            lambda name: name == REMOTE_BINDING_NAME,
        )
        bindings = client.get("/api/bindings").json()

    by_name = {binding["name"]: binding for binding in bindings}
    remote = by_name[REMOTE_BINDING_NAME]
    assert remote["is_remote"] is True
    assert remote["repo_name"] == "itastack"
    assert remote["claude_persist"] is True

    local = by_name["symphony"]
    assert local["is_remote"] is False
    assert local["repo_name"] is None
    assert local["claude_persist"] is False

    # Host grouping (#177): remote bindings group under their configured
    # remote.host; local bindings group under the server hostname. No DNS.
    assert remote["host"] == REMOTE_BINDING_NAME
    assert local["host"] == socket.gethostname().split(".", 1)[0]


def test_remote_bindings_on_same_host_share_group(monkeypatch, tmp_path: Path) -> None:
    # #177 ceiling fix: two repos on one remote host must collapse into ONE
    # sidebar group. Both carry the same configured remote.host.
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    from web.api.tests.conftest import REMOTE_BINDING_ENTRY

    second = {
        **REMOTE_BINDING_ENTRY,
        "name": "itastack2",
        "repo_path": "/home/itadmin/itastack2",
    }

    with TestClient(app) as client:
        login(client)
        monkeypatch.setattr(main, "_bindings_override", [REMOTE_BINDING_ENTRY, second])
        with main.connect(db_path) as connection:
            for name in ("n8n", "itastack2"):
                connection.execute(
                    "INSERT OR IGNORE INTO binding(name, display_name, sort_order) "
                    "VALUES (?, ?, 99)",
                    (name, name),
                )
            connection.commit()
        hosts = {
            b["name"]: b["host"]
            for b in client.get("/api/bindings").json()
            if b["name"] in ("n8n", "itastack2")
        }

    # Both repos declare remote.host=n8n -> one group.
    assert hosts["n8n"] == "n8n"
    assert hosts["itastack2"] == "n8n"


def test_remote_ip_host_bindings_group_by_host_alias(
    monkeypatch, tmp_path: Path
) -> None:
    # ADR-0039: when the SSH host is a raw IP, the display_name fallback splits
    # sibling bindings into separate sidebar groups. A shared remote.host_alias
    # collapses them back under one header without changing the SSH target.
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    first = {
        "name": "n8n",
        "repo_path": "/home/itadmin/itastack",
        "base_branch": "main",
        "type": "coding",
        "pi_mode": "rpc",
        "default_agent": "pi",
        "tracker": "podium",
        "remote": {"user": "itadmin", "host": "100.95.224.218", "host_alias": "n8n"},
    }
    second = {
        **first,
        "name": "n8n-dotfiles",
        "repo_path": "/home/itadmin/dotfiles",
    }

    with TestClient(app) as client:
        login(client)
        monkeypatch.setattr(main, "_bindings_override", [first, second])
        with main.connect(db_path) as connection:
            for name in ("n8n", "n8n-dotfiles"):
                connection.execute(
                    "INSERT OR IGNORE INTO binding(name, display_name, sort_order) "
                    "VALUES (?, ?, 99)",
                    (name, name),
                )
            connection.commit()
        hosts = {
            b["name"]: b["host"]
            for b in client.get("/api/bindings").json()
            if b["name"] in ("n8n", "n8n-dotfiles")
        }

    # Both raw-IP bindings share host_alias=n8n -> one "n8n" group.
    assert hosts["n8n"] == "n8n"
    assert hosts["n8n-dotfiles"] == "n8n"


def test_concurrent_reads_do_not_cross_threads(monkeypatch, tmp_path: Path) -> None:
    # Regression: FastAPI runs the sync get_connection dependency and the sync
    # endpoint in different anyio threadpool threads. Without
    # check_same_thread=False on the SQLite connection, concurrent requests hit
    # "SQLite objects created in a thread can only be used in that same thread"
    # and return 500. Fire many requests in parallel so the threadpool spreads
    # them across worker threads and the cross-thread path is exercised.
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        login(client)

        def fetch_bindings(_: int) -> int:
            return client.get("/api/bindings").status_code

        with ThreadPoolExecutor(max_workers=16) as pool:
            statuses = list(pool.map(fetch_bindings, range(64)))

    assert statuses == [200] * 64
