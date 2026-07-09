from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_CLIENT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "podium-issues-remote"
    / "create_issues.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("create_issues", _CLIENT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = _load_module()


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_capture(monkeypatch, *, start_id: int = 100):
    captured: list[dict] = []
    counter = {"next": start_id}

    def fake_urlopen(request):
        body = json.loads(request.data.decode("utf-8"))
        captured.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": body,
            }
        )
        issue_id = counter["next"]
        counter["next"] += 1
        return _FakeResponse({"id": issue_id})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    return captured


def _env(monkeypatch):
    monkeypatch.setenv("PODIUM_BASE_URL", "http://127.0.0.1:8090")
    monkeypatch.setenv("PODIUM_API_TOKEN", "test-token")
    monkeypatch.setenv("SYMPHONY_BINDING_NAME", "n8n")


def _spec(tmp_path: Path, slices: list[dict]) -> str:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"slices": slices}), encoding="utf-8")
    return str(path)


_TWO_SLICE = [
    {
        "key": "schema",
        "title": "Schema",
        "description": "Add columns.",
        "acceptance": ["columns exist"],
        "verification": "pytest -q",
        "locks": ["schema"],
    },
    {
        "key": "api",
        "title": "API",
        "description": "Wire API.",
        "acceptance": ["create works", "list works"],
        "verification": "pytest -q",
        "blocked_by": ["schema"],
    },
]


def test_blockers_post_before_dependents(tmp_path, monkeypatch):
    _env(monkeypatch)
    captured = _install_capture(monkeypatch)
    client.create_from_spec(_spec(tmp_path, _TWO_SLICE))
    titles = [c["body"]["description"].splitlines()[2] for c in captured]
    assert "Add columns." in titles[0]
    assert "Wire API." in titles[1]


def test_dependent_blocked_by_carries_returned_ids(tmp_path, monkeypatch):
    _env(monkeypatch)
    captured = _install_capture(monkeypatch, start_id=100)
    client.create_from_spec(_spec(tmp_path, _TWO_SLICE))
    assert captured[0]["body"]["blocked_by"] == []
    assert captured[1]["body"]["blocked_by"] == [100]


def test_description_folds_acceptance_and_flags(tmp_path, monkeypatch):
    _env(monkeypatch)
    captured = _install_capture(monkeypatch)
    client.create_from_spec(_spec(tmp_path, _TWO_SLICE))
    api_body = captured[1]["body"]
    assert "- [ ] create works" in api_body["description"]
    assert "- [ ] list works" in api_body["description"]
    assert "## Verification\n\npytest -q\n" in api_body["description"]
    assert api_body["auto_land"] is True
    assert api_body["worktree_active"] is True
    assert "origin" not in api_body
    assert captured[0]["headers"]["Authorization"] == "Bearer test-token"


def test_dry_run_issues_no_requests(tmp_path, monkeypatch, capsys):
    _env(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        client.urllib.request,
        "urlopen",
        lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError()),
    )
    client.create_from_spec(_spec(tmp_path, _TWO_SLICE), dry_run=True)
    assert calls == []
    assert "[dry-run]" in capsys.readouterr().out


def test_missing_env_fails_loud(tmp_path, monkeypatch):
    monkeypatch.delenv("PODIUM_BASE_URL", raising=False)
    monkeypatch.setenv("PODIUM_API_TOKEN", "t")
    monkeypatch.setenv("SYMPHONY_BINDING_NAME", "n8n")
    with pytest.raises(client.RemoteIssuesError, match="PODIUM_BASE_URL not set"):
        client.create_from_spec(_spec(tmp_path, _TWO_SLICE))


def test_dependency_cycle_raises(tmp_path, monkeypatch):
    _env(monkeypatch)
    _install_capture(monkeypatch)
    cyclic = [
        {
            "key": "a",
            "title": "A",
            "description": "",
            "acceptance": ["x"],
            "verification": "pytest -q",
            "blocked_by": ["b"],
        },
        {
            "key": "b",
            "title": "B",
            "description": "",
            "acceptance": ["x"],
            "verification": "pytest -q",
            "blocked_by": ["a"],
        },
    ]
    with pytest.raises(client.RemoteIssuesError, match="cycle"):
        client.create_from_spec(_spec(tmp_path, cyclic))
