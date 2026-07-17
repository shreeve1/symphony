"""API CRUD tests for binding-scoped automations (issue #4, ADR-0038).

Public seam pre-agreed by issue: binding-scoped HTTP CRUD API tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)
login = cast(Any, import_module("web.api.tests.conftest")).login


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    from web.api.title_generator import generate_issue_title as _real_generate

    def _fake_title(description, *, run_func=None):
        return _real_generate(description, run_func=lambda *a, **kw: _FakePiResult())

    monkeypatch.setattr(main._title_generator, "generate_issue_title", _fake_title)
    from web.api.tests.conftest import login

    with TestClient(app) as test_client:
        login(test_client)
        with main.connect(db_path) as connection:
            connection.executemany(
                "INSERT INTO skill(name, description, source) VALUES (?, ?, '')",
                [("/diagnose", "Diagnose fixture skill"), ("tdd", "TDD fixture skill")],
            )
            connection.commit()
        yield test_client


class _FakePiResult:
    returncode = 1
    stdout = ""


def _spawn_payload(**overrides):
    payload = {
        "mode": "spawn",
        "template_title": "Health check {binding}",
        "template_body": "Run patrol on {binding} every {interval}s",
        "spawn_interval_seconds": 3600,
    }
    payload.update(overrides)
    return payload


def _loop_payload(**overrides):
    payload = {
        "mode": "loop",
        "template_title": "Refactor {binding} module X",
        "template_body": "Iterative refactor of module X",
        "loop_iteration_cap": 5,
    }
    payload.update(overrides)
    return payload


def _assert_automation_shape(body):
    assert isinstance(body["id"], int)
    assert isinstance(body["binding_name"], str)
    assert body["mode"] in ("spawn", "loop")
    assert isinstance(body["enabled"], bool)
    assert isinstance(body["template_title"], str)
    assert isinstance(body["template_body"], str)
    assert "spawn_interval_seconds" in body
    assert "spawn_run_count" in body
    assert isinstance(body["occurrences_fired"], int)
    assert "next_fire_at" in body
    assert "loop_iteration_cap" in body
    assert isinstance(body["loop_completion_marker"], str)
    # Pin fields (issue #459) round-trip as nullable / bool.
    assert body["preferred_skill"] is None or isinstance(body["preferred_skill"], str)
    assert body["preferred_agent"] is None or isinstance(body["preferred_agent"], str)
    assert body["preferred_model"] is None or isinstance(body["preferred_model"], str)
    assert body["reasoning_effort"] is None or isinstance(body["reasoning_effort"], str)
    assert body["base_branch"] is None or isinstance(body["base_branch"], str)
    assert isinstance(body["worktree_active"], bool)
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


class TestCreate:
    def test_create_minimal_spawn(self, client):
        payload = _spawn_payload()
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        _assert_automation_shape(body)
        assert body["binding_name"] == "symphony"
        assert body["mode"] == "spawn"
        assert body["enabled"] is True
        assert body["template_title"] == "Health check {binding}"
        assert body["spawn_interval_seconds"] == 3600
        assert body["spawn_run_count"] is None
        assert body["occurrences_fired"] == 0
        assert body["next_fire_at"] is None
        assert body["loop_iteration_cap"] is None
        assert body["loop_completion_marker"] == "DONE.md"

    def test_create_spawn_with_run_count(self, client):
        payload = _spawn_payload(spawn_run_count=10)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["spawn_run_count"] == 10
        assert body["mode"] == "spawn"

    def test_create_spawn_start_immediately_default(self, client):
        # Issue #462: omitting start_delay_seconds leaves next_fire_at NULL so
        # the first issue fires on the next tick (today's default behaviour).
        payload = _spawn_payload()
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        assert resp.json()["next_fire_at"] is None

    def test_create_spawn_with_initial_delay(self, client):
        # Issue #462: start_delay_seconds sets next_fire_at ≈ now + delay.
        before = datetime.now(UTC)
        payload = _spawn_payload(start_delay_seconds=3600)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        next_fire_at = resp.json()["next_fire_at"]
        assert next_fire_at is not None
        fire_dt = datetime.fromisoformat(next_fire_at)
        expected = before + timedelta(seconds=3600)
        assert abs((fire_dt - expected).total_seconds()) < 60

    def test_reject_start_delay_on_loop(self, client):
        # Issue #462: start_delay_seconds is meaningless for loop mode.
        payload = _loop_payload(start_delay_seconds=3600)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422
        assert "start_delay_seconds" in str(resp.json()).lower()

    def test_reject_zero_start_delay(self, client):
        payload = _spawn_payload(start_delay_seconds=0)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_create_minimal_loop_coding_binding(self, client):
        payload = _loop_payload()
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        _assert_automation_shape(body)
        assert body["mode"] == "loop"
        assert body["loop_iteration_cap"] == 5
        assert body["loop_completion_marker"] == "DONE.md"
        assert body["spawn_interval_seconds"] is None

    def test_create_loop_custom_marker(self, client):
        payload = _loop_payload(loop_completion_marker="PROGRESS.md")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        assert resp.json()["loop_completion_marker"] == "PROGRESS.md"

    def test_create_loop_disabled(self, client):
        payload = _loop_payload(enabled=False)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        assert resp.json()["enabled"] is False

    def test_create_loop_coding_with_explicit_worktree_default(self, client):
        payload = _loop_payload()
        resp = client.post("/api/bindings/dotfiles/automations", json=payload)
        assert resp.status_code == 201

    def test_create_spawn_homelab_infra(self, client):
        payload = _spawn_payload()
        resp = client.post("/api/bindings/homelab/automations", json=payload)
        assert resp.status_code == 201

    def test_reject_loop_on_infra_binding(self, client):
        payload = _loop_payload()
        resp = client.post("/api/bindings/homelab/automations", json=payload)
        assert resp.status_code == 422
        detail = str(resp.json()).lower()
        assert "loop" in detail or "coding" in detail

    def test_reject_loop_on_remote_coding_binding(self, client):
        resp = client.post("/api/bindings/n8n/automations", json=_loop_payload())
        assert resp.status_code == 422

    def test_reject_spawn_without_interval(self, client):
        payload = _spawn_payload(spawn_interval_seconds=None)
        payload.pop("spawn_interval_seconds", None)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_spawn_zero_interval(self, client):
        payload = _spawn_payload(spawn_interval_seconds=0)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_spawn_negative_interval(self, client):
        payload = _spawn_payload(spawn_interval_seconds=-1)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_spawn_zero_run_count(self, client):
        payload = _spawn_payload(spawn_run_count=0)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_spawn_negative_run_count(self, client):
        payload = _spawn_payload(spawn_run_count=-5)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_loop_without_iteration_cap(self, client):
        payload = _loop_payload(loop_iteration_cap=None)
        payload.pop("loop_iteration_cap", None)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_loop_zero_iteration_cap(self, client):
        payload = _loop_payload(loop_iteration_cap=0)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_loop_negative_iteration_cap(self, client):
        payload = _loop_payload(loop_iteration_cap=-1)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_loop_empty_completion_marker(self, client):
        payload = _loop_payload(loop_completion_marker="")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_loop_path_traversal_marker(self, client):
        payload = _loop_payload(loop_completion_marker="../../etc/passwd")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_loop_absolute_marker(self, client):
        payload = _loop_payload(loop_completion_marker="/etc/passwd")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_missing_binding(self, client):
        payload = _spawn_payload()
        resp = client.post("/api/bindings/nonexistent/automations", json=payload)
        assert resp.status_code == 404

    def test_reject_unknown_mode(self, client):
        payload = _spawn_payload(mode="unknown")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_reject_extra_field(self, client):
        payload = _spawn_payload(unknown_field="wat")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 400


class TestList:
    def test_list_empty(self, client):
        resp = client.get("/api/bindings/symphony/automations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_all_for_binding(self, client):
        c1 = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        c2 = client.post(
            "/api/bindings/symphony/automations",
            json=_spawn_payload(template_title="Second"),
        ).json()
        resp = client.get("/api/bindings/symphony/automations")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()]
        assert c1["id"] in ids
        assert c2["id"] in ids

    def test_list_scoped_to_binding(self, client):
        client.post("/api/bindings/symphony/automations", json=_spawn_payload()).json()
        resp = client.get("/api/bindings/homelab/automations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_unknown_binding_404(self, client):
        resp = client.get("/api/bindings/nonexistent/automations")
        assert resp.status_code == 404


class TestGet:
    def test_get_by_id(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.get(f"/api/bindings/symphony/automations/{created['id']}")
        assert resp.status_code == 200
        assert resp.json() == created

    def test_get_not_found(self, client):
        resp = client.get("/api/bindings/symphony/automations/99999")
        assert resp.status_code == 404

    def test_get_wrong_binding_scoped(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.get(f"/api/bindings/homelab/automations/{created['id']}")
        assert resp.status_code == 404

    def test_get_unknown_binding_404(self, client):
        resp = client.get("/api/bindings/nonexistent/automations/1")
        assert resp.status_code == 404


class TestPatch:
    def test_patch_title(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"template_title": "Updated title"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["template_title"] == "Updated title"
        assert body["template_body"] == created["template_body"]

    def test_patch_toggle_enabled(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        assert created["enabled"] is True
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_patch_enabled_back_on(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload(enabled=False)
        ).json()
        assert created["enabled"] is False
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_patch_spawn_interval(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"spawn_interval_seconds": 7200},
        )
        assert resp.status_code == 200
        assert resp.json()["spawn_interval_seconds"] == 7200

    def test_patch_spawn_run_count(self, client):
        created = client.post(
            "/api/bindings/symphony/automations",
            json=_spawn_payload(spawn_run_count=10),
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"spawn_run_count": 20},
        )
        assert resp.status_code == 200
        assert resp.json()["spawn_run_count"] == 20

    def test_patch_spawn_run_count_to_unlimited(self, client):
        created = client.post(
            "/api/bindings/symphony/automations",
            json=_spawn_payload(spawn_run_count=10),
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"spawn_run_count": None},
        )
        assert resp.status_code == 200
        assert resp.json()["spawn_run_count"] is None

    def test_patch_loop_iteration_cap(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_loop_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"loop_iteration_cap": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["loop_iteration_cap"] == 10

    def test_patch_loop_marker(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_loop_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"loop_completion_marker": "COMPLETE.md"},
        )
        assert resp.status_code == 200
        assert resp.json()["loop_completion_marker"] == "COMPLETE.md"

    def test_patch_not_found(self, client):
        resp = client.patch(
            "/api/bindings/symphony/automations/99999", json={"template_title": "Nope"}
        )
        assert resp.status_code == 404

    def test_patch_wrong_binding_scoped(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/homelab/automations/{created['id']}",
            json={"template_title": "Nope"},
        )
        assert resp.status_code == 404

    def test_patch_reject_extra_field(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"unknown_field": "wat"},
        )
        assert resp.status_code == 400

    def test_patch_spawn_rejects_zero_interval(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"spawn_interval_seconds": 0},
        )
        assert resp.status_code == 422

    def test_patch_loop_rejects_zero_cap(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_loop_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"loop_iteration_cap": 0},
        )
        assert resp.status_code == 422

    def test_patch_loop_rejects_empty_marker(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_loop_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"loop_completion_marker": ""},
        )
        assert resp.status_code == 422

    def test_patch_cannot_change_mode(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}", json={"mode": "loop"}
        )
        assert resp.status_code == 400


class TestDelete:
    def test_delete_existing(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.delete(f"/api/bindings/symphony/automations/{created['id']}")
        assert resp.status_code == 200
        get_resp = client.get(f"/api/bindings/symphony/automations/{created['id']}")
        assert get_resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/api/bindings/symphony/automations/99999")
        assert resp.status_code == 404

    def test_delete_wrong_binding(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.delete(f"/api/bindings/homelab/automations/{created['id']}")
        assert resp.status_code == 404
        get_resp = client.get(f"/api/bindings/symphony/automations/{created['id']}")
        assert get_resp.status_code == 200


class TestCascade:
    def test_automation_has_on_delete_cascade_fk(self, client):
        """Verify the automation table has ON DELETE CASCADE FK to binding."""
        with main.connect() as connection:
            fks = connection.execute("PRAGMA foreign_key_list(automation)").fetchall()
            assert any(
                row["table"] == "binding" and row["on_delete"].lower() == "cascade"
                for row in fks
            )


class TestPinFields:
    """Round-trip the per-Issue dispatch pin fields (issue #459).

    Each pin field is nullable and round-trips through AutomationCreate /
    AutomationPatch / GET. The tracker_podium fire paths are covered
    separately in tests/test_tracker_podium.py.
    """

    def test_create_with_all_pins_spawn(self, client):
        payload = _spawn_payload(
            preferred_skill="homelab-operations",
            preferred_agent="pi",
            preferred_model="pi-duo/Duo",
            reasoning_effort="xhigh",
            base_branch="develop",
            worktree_active=True,
        )
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["preferred_skill"] == "homelab-operations"
        assert body["preferred_agent"] == "pi"
        assert body["preferred_model"] == "pi-duo/Duo"
        assert body["reasoning_effort"] == "xhigh"
        assert body["base_branch"] == "develop"
        assert body["worktree_active"] is True

    def test_create_with_all_pins_loop(self, client):
        payload = _loop_payload(
            preferred_skill="diagnose",
            preferred_agent="pi",
            preferred_model="deepseek-v4-flash",
            reasoning_effort="low",
            base_branch="main",
            worktree_active=True,  # loops require True on create (Q4)
        )
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["preferred_skill"] == "diagnose"
        assert body["preferred_agent"] == "pi"
        assert body["preferred_model"] == "deepseek-v4-flash"
        assert body["reasoning_effort"] == "low"
        assert body["base_branch"] == "main"
        assert body["worktree_active"] is True

    def test_loop_rejects_explicit_worktree_active_false(self, client):
        # Issue #461 (Q4): loops always run inside a persistent worktree;
        # explicit False is rejected at the API gate instead of being
        # silently overwritten by the fire path.
        payload = _loop_payload(worktree_active=False)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422
        assert "worktree_active" in resp.text

    def test_loop_accepts_worktree_active_omitted(self, client):
        # Issue #461 (Q4): the form omits worktree_active for loops and
        # sends true explicitly; the default-omitted path must still work
        # (server-side default isn't a rejection trigger).
        payload = _loop_payload()
        payload.pop("worktree_active", None)
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        assert resp.json()["worktree_active"] is False  # default; fire path forces True

    def test_loop_patch_rejects_worktree_active_false(self, client):
        # Issue #461 (Q4): PATCHing a loop row's worktree_active to False
        # is a 422. Loops store True (the column value matches the fire-
        # path output) and any explicit downgrade is rejected at the API.
        created = client.post(
            "/api/bindings/symphony/automations",
            json=_loop_payload(worktree_active=True),
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"worktree_active": False},
        )
        assert resp.status_code == 422
        assert "worktree_active" in resp.text

    def test_create_pins_default_null(self, client):
        payload = _spawn_payload()
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["preferred_skill"] is None
        assert body["preferred_agent"] is None
        assert body["preferred_model"] is None
        assert body["reasoning_effort"] is None
        assert body["base_branch"] is None
        assert body["worktree_active"] is False

    def test_reject_invalid_effort(self, client):
        payload = _spawn_payload(reasoning_effort="ultra")
        resp = client.post("/api/bindings/symphony/automations", json=payload)
        assert resp.status_code == 422

    def test_patch_each_pin_independently(self, client):
        created = client.post(
            "/api/bindings/symphony/automations", json=_spawn_payload()
        ).json()
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={
                "preferred_skill": "tdd",
                "preferred_agent": "claude",
                "preferred_model": "claude-opus-4-8",
                "reasoning_effort": "medium",
                "base_branch": "feature",
                "worktree_active": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["preferred_skill"] == "tdd"
        assert body["preferred_agent"] == "claude"
        assert body["preferred_model"] == "claude-opus-4-8"
        assert body["reasoning_effort"] == "medium"
        assert body["base_branch"] == "feature"
        assert body["worktree_active"] is True

    def test_patch_clear_base_branch_with_null(self, client):
        created = client.post(
            "/api/bindings/symphony/automations",
            json=_spawn_payload(base_branch="develop"),
        ).json()
        assert created["base_branch"] == "develop"
        resp = client.patch(
            f"/api/bindings/symphony/automations/{created['id']}",
            json={"base_branch": None},
        )
        assert resp.status_code == 200
        assert resp.json()["base_branch"] is None

    def test_list_includes_pin_fields(self, client):
        client.post(
            "/api/bindings/symphony/automations",
            json=_spawn_payload(preferred_model="pi-duo/Duo"),
        ).json()
        resp = client.get("/api/bindings/symphony/automations")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert "preferred_skill" in rows[0]
        assert "preferred_agent" in rows[0]
        assert "preferred_model" in rows[0]
        assert "reasoning_effort" in rows[0]
        assert "base_branch" in rows[0]
        assert "worktree_active" in rows[0]


class TestMigrationParity:
    def test_automation_table_exists_in_schema(self, client):
        with main.connect() as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )
            ]
            assert "automation" in tables
            cols = {
                row[1]: row[2]
                for row in connection.execute("PRAGMA table_info(automation)")
            }
            assert cols["id"] == "INTEGER"
            assert cols["binding_name"] == "TEXT"
            assert cols["mode"] == "TEXT"
            assert cols["enabled"] == "BOOLEAN"
            assert cols["template_title"] == "TEXT"
            assert cols["template_body"] == "TEXT"
            assert cols["spawn_interval_seconds"] == "INTEGER"
            assert cols["spawn_run_count"] == "INTEGER"
            assert cols["occurrences_fired"] == "INTEGER"
            assert cols["next_fire_at"] == "TIMESTAMP"
            assert cols["loop_iteration_cap"] == "INTEGER"
            assert cols["loop_completion_marker"] == "TEXT"
            # Pin fields (issue #459, migration 0023)
            assert cols["preferred_skill"] == "TEXT"
            assert cols["preferred_agent"] == "TEXT"
            assert cols["preferred_model"] == "TEXT"
            assert cols["reasoning_effort"] == "TEXT"
            assert cols["base_branch"] == "TEXT"
            assert cols["worktree_active"] == "BOOLEAN"
            assert cols["created_at"] == "TIMESTAMP"
            assert cols["updated_at"] == "TIMESTAMP"
