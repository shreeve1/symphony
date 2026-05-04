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
            "/api/v1/workspaces/homelab/projects/cff68c17-bff6-452f-89b3-9b570613cfaa/issues/issue-123",
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
            "/api/v1/workspaces/homelab/projects/cff68c17-bff6-452f-89b3-9b570613cfaa/issues/issue-123/comments",
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


def test_urllib_transport_sets_authorization_header(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.headers["Authorization"]
        captured["content_type"] = request.headers["Content-type"]
        captured["body"] = request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    config = PlaneCliConfig.from_env(_env())
    transport = UrllibTransport(config)

    transport.patch(config.issue_path(), {"state": STATE_IDS["review"]})

    assert captured["url"].endswith("/issues/issue-123")
    assert captured["method"] == "PATCH"
    assert captured["authorization"] == "Bearer fake-plane-key-for-tests"
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


def test_state_identifiers_match_issue_025_plane_contract_resolution():
    assert STATE_IDS == {
        "done": "ef9d22b5-c69c-4707-8ba3-e3db244f2a84",
        "review": "ea1ccd3d-82d3-4dd4-8226-192941e8e4c0",
        "blocked": "4b226b00-1e1c-46aa-bbd3-b1e04ad6fc1f",
    }
