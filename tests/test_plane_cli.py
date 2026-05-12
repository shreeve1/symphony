import os
import subprocess
from pathlib import Path
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


def test_comment_subcommand_bounds_long_comment_text():
    transport = MockTransport()
    long_comment = "summary line " + ("verbose output " * 300)

    assert run(["plane", "comment", long_comment], env=_env(), transport=transport) == 0

    posted = transport.calls[0][2]["comment_html"]
    assert "Agent comment truncated from" in posted
    assert posted.startswith("summary line")
    assert len(posted) < len(long_comment)
    assert len(posted) < 1700


def test_comment_subcommand_strips_ansi_and_redacts_known_secrets():
    transport = MockTransport()

    assert (
        run(
            ["plane", "comment", "\x1b[31mkey=fake-plane-key-for-tests\x1b[0m"],
            env=_env(),
            transport=transport,
        )
        == 0
    )

    posted = transport.calls[0][2]["comment_html"]
    assert "\x1b" not in posted
    assert "fake-plane-key-for-tests" not in posted
    assert "***REDACTED***" in posted


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


def test_file_has_python_shebang():
    source = Path("/home/james/plane/symphony/plane_cli.py").read_text(encoding="utf-8")

    assert source.startswith("#!/usr/bin/env python3\n")


def test_plane_cli_copy_runs_as_path_executable_with_pythonpath(tmp_path: Path):
    source = Path("/home/james/plane/symphony/plane_cli.py")
    target = tmp_path / "plane"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o700)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(source.parent),
    }

    result = subprocess.run(
        [str(target), "done"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 1
    assert "Missing required environment variables" in result.stderr
    assert "Exec format error" not in result.stderr
    assert "ImportError" not in result.stderr


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
        "todo": PlaneState.TODO,
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


def test_comments_command_bounds_long_historical_comments(capsys):
    transport = MockTransport()
    transport._comments = [
        {
            "comment_html": "historical summary\n" + "verbose historical output\n" * 300,
            "created_at": "2026-05-04T01:00:00Z",
        }
    ]

    assert run(["plane", "comments"], env=_env(), transport=transport) == 0

    output = capsys.readouterr().out
    assert "Plane comment truncated from" in output
    assert output.count("verbose historical output") < 40


def test_comments_command_redacts_known_secrets(capsys):
    transport = MockTransport()
    transport._comments = [
        {"comment_html": "key=fake-plane-key-for-tests", "created_at": "2026-05-04T01:00:00Z"}
    ]

    assert run(["plane", "comments"], env=_env(), transport=transport) == 0

    output = capsys.readouterr().out
    assert "fake-plane-key-for-tests" not in output
    assert "***REDACTED***" in output


def test_comments_command_with_no_comments_shows_empty(capsys):
    transport = MockTransport()

    assert run(["plane", "comments"], env=_env(), transport=transport) == 0

    output = capsys.readouterr().out
    assert output == ""


# ---------------------------------------------------------------------------
# Wave 3: plane schedule / plane unschedule
# ---------------------------------------------------------------------------


_ISSUE_PATH = (
    "/api/v1/workspaces/homelab/projects/"
    "cff68c17-bff6-452f-89b3-9b570613cfaa/issues/issue-123/"
)
_COMMENT_PATH = _ISSUE_PATH + "comments/"


def test_schedule_command_posts_comment_adds_label_and_transitions_todo():
    transport = MockTransport()
    transport._issues["issue-123"] = {"labels": ["other-uuid"]}

    rc = run(
        [
            "plane",
            "schedule",
            "--not-before",
            "2026-05-08T20:00:00Z",
            "--reason",
            "wait for change window",
        ],
        env=_env(),
        transport=transport,
    )

    assert rc == 0
    # Expect: POST comment, PATCH labels (add scheduled), PATCH state -> Todo.
    assert len(transport.calls) == 3
    method, path, body = transport.calls[0]
    assert method == "POST"
    assert path == _COMMENT_PATH
    assert body["comment_html"].startswith("Symphony-Schedule: ")
    assert "not_before=2026-05-08T20:00:00+00:00" in body["comment_html"]
    assert 'reason="wait for change window"' in body["comment_html"]

    method, path, body = transport.calls[1]
    assert method == "PATCH"
    assert path == _ISSUE_PATH
    assert plane_cli.LABEL_IDS["scheduled"] in body["labels"]
    assert "other-uuid" in body["labels"]

    method, path, body = transport.calls[2]
    assert method == "PATCH"
    assert path == _ISSUE_PATH
    assert body == {"state": plane_cli.STATE_IDS["todo"]}


def test_schedule_command_sends_telegram_when_configured(monkeypatch):
    transport = MockTransport()
    captured = {}

    class FakeResponse:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = __import__("json").loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    rc = run(
        [
            "plane",
            "schedule",
            "--not-before",
            "2026-05-08T20:00:00Z",
            "--reason",
            "wait <window>",
        ],
        env=_env({"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"}),
        transport=transport,
    )

    assert rc == 0
    assert "bottok/sendMessage" in captured["url"]
    assert captured["payload"]["chat_id"] == "chat"
    assert captured["payload"]["parse_mode"] == "HTML"
    assert "Scheduled" in captured["payload"]["text"]
    assert "&lt;window&gt;" in captured["payload"]["text"]


def test_schedule_command_includes_optional_not_after():
    transport = MockTransport()

    rc = run(
        [
            "plane",
            "schedule",
            "--not-before",
            "2026-05-08T20:00:00Z",
            "--not-after",
            "2026-05-08T22:00:00Z",
            "--reason",
            "window",
        ],
        env=_env(),
        transport=transport,
    )

    assert rc == 0
    method, path, body = transport.calls[0]
    assert method == "POST"
    assert "not_after=2026-05-08T22:00:00+00:00" in body["comment_html"]


def test_schedule_command_supports_equals_form():
    transport = MockTransport()

    rc = run(
        [
            "plane",
            "schedule",
            "--not-before=2026-05-08T20:00:00Z",
            "--reason=wait",
        ],
        env=_env(),
        transport=transport,
    )

    assert rc == 0
    assert transport.calls[0][0] == "POST"


def test_schedule_command_rejects_naive_datetime():
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="UTC offset|ISO 8601"):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T20:00:00",
                "--reason",
                "wait",
            ],
            env=_env(),
            transport=transport,
        )
    # No mutation should have happened.
    assert transport.calls == []


def test_schedule_command_rejects_inverted_window():
    transport = MockTransport()

    with pytest.raises(ValueError, match="not_after must be >= not_before"):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T22:00:00Z",
                "--not-after",
                "2026-05-08T20:00:00Z",
                "--reason",
                "wait",
            ],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_schedule_command_rejects_empty_reason():
    transport = MockTransport()

    with pytest.raises(ValueError, match="reason"):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T20:00:00Z",
                "--reason",
                "   ",
            ],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_schedule_command_requires_not_before_and_reason():
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="Missing required option"):
        run(["plane", "schedule", "--reason", "wait"], env=_env(), transport=transport)

    with pytest.raises(PlaneCliError, match="Missing required option"):
        run(
            ["plane", "schedule", "--not-before", "2026-05-08T20:00:00Z"],
            env=_env(),
            transport=transport,
        )


def test_schedule_command_rejects_unknown_options():
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="Unknown option"):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T20:00:00Z",
                "--reason",
                "wait",
                "--owner",
                "me",
            ],
            env=_env(),
            transport=transport,
        )


def test_schedule_command_rejects_target_override():
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="target override"):
        run(
            [
                "plane",
                "schedule",
                "--issue",
                "other-issue",
                "--not-before",
                "2026-05-08T20:00:00Z",
                "--reason",
                "wait",
            ],
            env=_env(),
            transport=transport,
        )


def test_unschedule_command_posts_comment_and_removes_label():
    transport = MockTransport()
    scheduled_uuid = plane_cli.LABEL_IDS["scheduled"]
    transport._issues["issue-123"] = {"labels": [scheduled_uuid, "other-uuid"]}

    rc = run(
        ["plane", "unschedule", "--reason", "owner cancelled"],
        env=_env(),
        transport=transport,
    )

    assert rc == 0
    # Expect: POST comment, PATCH labels (remove scheduled). NO state PATCH.
    assert len(transport.calls) == 2
    method, path, body = transport.calls[0]
    assert method == "POST"
    assert path == _COMMENT_PATH
    assert body["comment_html"].startswith("Symphony-Schedule-Cancelled: ")
    assert 'reason="owner cancelled"' in body["comment_html"]

    method, path, body = transport.calls[1]
    assert method == "PATCH"
    assert path == _ISSUE_PATH
    assert scheduled_uuid not in body["labels"]
    assert "other-uuid" in body["labels"]


def test_unschedule_command_rejects_empty_reason():
    transport = MockTransport()

    with pytest.raises(ValueError, match="reason"):
        run(
            ["plane", "unschedule", "--reason", ""],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_unschedule_command_requires_reason():
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="Missing required option"):
        run(["plane", "unschedule"], env=_env(), transport=transport)


def test_unschedule_command_rejects_target_override():
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="target override"):
        run(
            ["plane", "unschedule", "--issue=other", "--reason", "x"],
            env=_env(),
            transport=transport,
        )


def test_schedule_command_fails_fast_when_scheduled_label_missing(monkeypatch):
    """Plan task 4.7: fail fast if generated IDs lack scheduled."""
    monkeypatch.setattr(
        plane_cli, "LABEL_IDS", {k: v for k, v in plane_cli.LABEL_IDS.items() if k != "scheduled"}
    )
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="missing the 'scheduled' label"):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T20:00:00Z",
                "--reason",
                "wait",
            ],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_schedule_command_fails_fast_when_todo_state_missing(monkeypatch):
    """Plan task 4.7: fail fast if generated IDs lack todo state."""
    monkeypatch.setattr(
        plane_cli, "STATE_IDS", {k: v for k, v in plane_cli.STATE_IDS.items() if k != "todo"}
    )
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="missing the 'todo' state"):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T20:00:00Z",
                "--reason",
                "wait",
            ],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_unschedule_command_fails_fast_when_scheduled_label_missing(monkeypatch):
    monkeypatch.setattr(
        plane_cli, "LABEL_IDS", {k: v for k, v in plane_cli.LABEL_IDS.items() if k != "scheduled"}
    )
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="missing the 'scheduled' label"):
        run(
            ["plane", "unschedule", "--reason", "x"],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_unschedule_command_fails_fast_when_todo_state_missing(monkeypatch):
    monkeypatch.setattr(
        plane_cli, "STATE_IDS", {k: v for k, v in plane_cli.STATE_IDS.items() if k != "todo"}
    )
    transport = MockTransport()

    with pytest.raises(PlaneCliError, match="missing the 'todo' state"):
        run(
            ["plane", "unschedule", "--reason", "x"],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []


def test_schedule_validates_before_any_mutation():
    """If validation fails (e.g. naive datetime), no Plane API calls happen.

    Plan task 4.3: validate locally before mutation so partial failure
    can't leave the ticket in an inconsistent state.
    """
    transport = MockTransport()

    with pytest.raises((PlaneCliError, ValueError)):
        run(
            [
                "plane",
                "schedule",
                "--not-before",
                "2026-05-08T20:00:00",  # naive: rejected by format_schedule_comment
                "--reason",
                "x",
            ],
            env=_env(),
            transport=transport,
        )
    assert transport.calls == []
