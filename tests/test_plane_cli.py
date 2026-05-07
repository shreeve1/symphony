import urllib.error

import pytest

import plane_cli
from plane_cli import STATE_IDS, PlaneCliError, PlaneCliConfig, UrllibTransport, run


def _env(overrides=None):
    env = {
        "SYMPHONY_ISSUE_ID": "issue-123",
        "SYMPHONY_PLANE_API_URL": "https://plane.example.test",
        "SYMPHONY_PLANE_API_KEY": "fake-plane-key-for-tests",
        "SYMPHONY_PLANE_PROJECT_ID": "cff68c17-bff6-452f-89b3-9b570613cfaa",
        "SYMPHONY_PLANE_WORKSPACE_SLUG": "homelab",
    }
    if overrides:
        env.update(overrides)
    return env


class MockTransport:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
        self._issues: dict[str, dict] = {}
        self._comments: list[dict] = []

    def get(self, path, body=None):
        if self.fail:
            raise PlaneCliError("Plane API error: HTTP 500")
        if "comments" in path:
            return {"results": self._comments}
        for issue_id, issue in self._issues.items():
            if issue_id in path:
                return issue
        return {"labels": []}

    def patch(self, path, body):
        if self.fail:
            raise PlaneCliError("Plane API error: HTTP 500")
        self.calls.append(("PATCH", path, body))

    def post(self, path, body):
        if self.fail:
            raise PlaneCliError("Plane API error: HTTP 500")
        self.calls.append(("POST", path, body))


@pytest.mark.parametrize(
    ("command", "state_id"),
    [
        (["plane", "done"], STATE_IDS["done"]),
        (["plane", "review"], STATE_IDS["review"]),
        (["plane", "blocked"], STATE_IDS["blocked"]),
    ],
)
def test_state_subcommands_transition_expected_state(command, state_id):
    transport = MockTransport()

    assert run(command, env=_env(), transport=transport) == 0

    assert transport.calls == [
        (
            "PATCH",
            "/api/v1/workspaces/homelab/projects/cff68c17-bff6-452f-89b3-9b570613cfaa/issues/issue-123/",
            {"state": state_id},
        )
    ]


def test_comment_subcommand_posts_comment_text_to_env_issue():
    transport = MockTransport()

    assert (
        run(["plane", "comment", "ready", "for", "review"], env=_env(), transport=transport)
        == 0
    )

    assert transport.calls == [
        (
            "POST",
            "/api/v1/workspaces/homelab/projects/cff68c17-bff6-452f-89b3-9b570613cfaa/issues/issue-123/comments/",
            {"comment_html": "ready for review"},
        )
    ]


def test_missing_env_vars_are_reported_together():
    env = _env({"SYMPHONY_ISSUE_ID": "", "SYMPHONY_PLANE_API_KEY": ""})

    with pytest.raises(PlaneCliError) as excinfo:
        run(["plane", "done"], env=env, transport=MockTransport())

    message = str(excinfo.value)
    assert "SYMPHONY_ISSUE_ID" in message
    assert "SYMPHONY_PLANE_API_KEY" in message


def test_plane_api_error_exits_nonzero_through_main(monkeypatch, capsys):
    class FailingTransport:
        def __init__(self, config):
            pass

        def patch(self, path, body):
            raise PlaneCliError("Plane API error: HTTP 500")

        def post(self, path, body):
            raise AssertionError("unexpected comment post")

    monkeypatch.setattr(plane_cli, "UrllibTransport", FailingTransport)
    monkeypatch.setattr(plane_cli.os, "environ", _env())

    assert plane_cli.main(["plane", "done"]) == 1
    assert "Plane API error" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flag",
    [
        "--issue",
        "--issue=other",
        "--issue-id",
        "--issue-id=other",
        "--target",
        "--target=other",
        "--target-issue",
        "--target-issue=other",
    ],
)
def test_rejects_attempts_to_target_other_issues(flag):
    args = ["plane", "done", flag]
    if not flag.endswith("other"):
        args.append("other")

    with pytest.raises(PlaneCliError, match="Issue target override is not allowed"):
        run(args, env=_env(), transport=MockTransport())


def test_state_commands_reject_positional_issue_argument():
    with pytest.raises(PlaneCliError, match="does not accept an issue argument"):
        run(["plane", "done", "other-issue"], env=_env(), transport=MockTransport())


def test_runtime_script_has_no_symphony_imports():
    source = open("/home/james/plane/symphony/plane_cli.py", encoding="utf-8").read()

    assert "import symphony" not in source
    assert "from symphony" not in source


def test_urllib_transport_sets_plane_api_key_header(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["api_key"] = request.headers["X-api-key"]
        captured["authorization"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers["Content-type"]
        captured["body"] = request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    config = PlaneCliConfig.from_env(_env())
    transport = UrllibTransport(config)

    transport.patch(config.issue_path(), {"state": STATE_IDS["review"]})

    assert captured["url"].endswith("/issues/issue-123/")
    assert captured["method"] == "PATCH"
    assert captured["api_key"] == "fake-plane-key-for-tests"
    assert captured["authorization"] is None
    assert captured["content_type"] == "application/json"
    assert captured["timeout"] == 30


def test_urllib_transport_maps_http_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    config = PlaneCliConfig.from_env(_env())
    transport = UrllibTransport(config)

    with pytest.raises(PlaneCliError, match="Plane API error: HTTP 403"):
        transport.patch(config.issue_path(), {"state": STATE_IDS["blocked"]})


def test_urllib_transport_maps_url_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("fake connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    config = PlaneCliConfig.from_env(_env())
    transport = UrllibTransport(config)

    with pytest.raises(PlaneCliError, match="Plane API error: fake connection refused"):
        transport.post(config.comment_path(), {"comment_html": "blocked"})


def _import_plane_contract():
    """Import plane_contract using the same fallback pattern as plane_poller.

    plane_cli is intentionally standalone (urllib only) so the contract
    test loads plane_contract here, not in plane_cli itself.
    """
    import os
    import sys
    from pathlib import Path

    try:
        from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneState
    except ModuleNotFoundError:
        repo_env = os.environ.get("HOMELAB_REPO_PATH", "/home/james/homelab")
        src = Path(repo_env) / "automation" / "homelab-stack" / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneState
    return DEFAULT_CONTRACT, PlaneState


def test_state_ids_match_plane_contract_default_contract():
    """plane_cli.STATE_IDS must match DEFAULT_CONTRACT.state_ids.

    plane_cli keys by command verb (done/review/blocked); plane_contract keys
    by PlaneState enum. Drift here means the generator (scripts/sync_plane_ids.py)
    was not run after a contract change.
    """
    DEFAULT_CONTRACT, PlaneState = _import_plane_contract()
    state_key_map = {
        "done": PlaneState.DONE,
        "review": PlaneState.IN_REVIEW,
        "blocked": PlaneState.BLOCKED,
    }
    expected = {verb: DEFAULT_CONTRACT.state_ids[state] for verb, state in state_key_map.items()}
    assert STATE_IDS == expected, (
        "plane_cli.STATE_IDS drifted from plane_contract.DEFAULT_CONTRACT. "
        "Re-run scripts/sync_plane_ids.py to regenerate."
    )


def test_label_ids_match_plane_contract_default_contract():
    """plane_cli.LABEL_IDS must match DEFAULT_CONTRACT.label_ids exactly."""
    DEFAULT_CONTRACT, _ = _import_plane_contract()
    assert plane_cli.LABEL_IDS == DEFAULT_CONTRACT.label_ids, (
        "plane_cli.LABEL_IDS drifted from plane_contract.DEFAULT_CONTRACT. "
        "Re-run scripts/sync_plane_ids.py to regenerate."
    )


def test_label_command_patches_labels_correctly():
    transport = MockTransport()
    transport._issues["issue-123"] = {"labels": ["existing-uuid"]}

    assert run(["plane", "label", "plan"], env=_env(), transport=transport) == 0

    assert len(transport.calls) == 1
    method, path, body = transport.calls[0]
    assert method == "PATCH"
    label_uuid = plane_cli.LABEL_IDS["plan"]
    assert label_uuid in body["labels"]
    assert "existing-uuid" in body["labels"]


def test_unlabel_command_removes_label_correctly():
    transport = MockTransport()
    plan_uuid = plane_cli.LABEL_IDS["plan"]
    transport._issues["issue-123"] = {"labels": [plan_uuid, "other-uuid"]}

    assert run(["plane", "unlabel", "plan"], env=_env(), transport=transport) == 0

    assert len(transport.calls) == 1
    method, path, body = transport.calls[0]
    assert method == "PATCH"
    assert plan_uuid not in body["labels"]
    assert "other-uuid" in body["labels"]


def test_label_command_rejects_unknown_label():
    transport = MockTransport()
    with pytest.raises(PlaneCliError, match="Unknown label"):
        run(["plane", "label", "nonexistent"], env=_env(), transport=transport)


def test_unlabel_command_rejects_unknown_label():
    transport = MockTransport()
    with pytest.raises(PlaneCliError, match="Unknown label"):
        run(["plane", "unlabel", "nonexistent"], env=_env(), transport=transport)


def test_comments_command_displays_comments_oldest_first(capsys):
    transport = MockTransport()
    transport._comments = [
        {"comment_html": "second comment", "created_at": "2026-05-04T02:00:00Z"},
        {"comment_html": "first comment", "created_at": "2026-05-04T01:00:00Z"},
    ]

    assert run(["plane", "comments"], env=_env(), transport=transport) == 0

    output = capsys.readouterr().out
    assert output.index("first comment") < output.index("second comment")
    assert "---" in output


def test_comments_command_with_no_comments_shows_empty(capsys):
    transport = MockTransport()

    assert run(["plane", "comments"], env=_env(), transport=transport) == 0

    output = capsys.readouterr().out
    assert output == ""
