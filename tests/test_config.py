from pathlib import Path

import pytest

from config import ConfigError, SymphonyConfig, _truthy
from plane_adapter import InMemoryTransport, build_adapter
from tracker_contract import TrackerRole

_NO_BINDINGS_YML = "/nonexistent/symphony-bindings.yml"


def _env(**overrides):
    env = {
        "PLANE_API_URL": "http://plane.example.test",
        "PLANE_API_KEY": "fake-plane-key-for-tests",
        "PLANE_WORKSPACE_SLUG": "homelab",
        "PLANE_PROJECT_ID": "fake-project-uuid",
        "HOMELAB_REPO_PATH": "/home/james/homelab",
        "PI_BIN": "/usr/local/bin/pi",
        "SYMPHONY_BINDINGS_PATH": _NO_BINDINGS_YML,
    }
    env.update(overrides)
    return env


def _tracker_env(**overrides):
    env = {
        "SYMPHONY_TRACKER_API_URL": "http://tracker.example.test",
        "SYMPHONY_TRACKER_API_KEY": "fake-tracker-key-for-tests",
        "SYMPHONY_TRACKER_WORKSPACE_SLUG": "tracker-workspace",
        "SYMPHONY_TRACKER_PROJECT_ID": "fake-tracker-project-uuid",
        "HOMELAB_REPO_PATH": "/home/james/tracker-repo",
        "PI_BIN": "/usr/local/bin/pi",
        "SYMPHONY_BINDINGS_PATH": _NO_BINDINGS_YML,
    }
    env.update(overrides)
    return env


def test_from_env_lists_all_missing_required_vars():
    with pytest.raises(EnvironmentError) as exc:
        SymphonyConfig.from_env({"SYMPHONY_BINDINGS_PATH": _NO_BINDINGS_YML})

    message = str(exc.value)
    assert "PLANE_API_URL" in message
    assert "PLANE_API_KEY" in message
    assert "PLANE_WORKSPACE_SLUG" in message
    assert "PLANE_PROJECT_ID" in message
    assert "HOMELAB_REPO_PATH" in message
    assert "PI_BIN" in message
    assert "OPEN" + "CODE_BIN" not in message


def test_from_env_loads_legacy_plane_env_values_with_optional_defaults():
    config = SymphonyConfig.from_env(_env())

    assert config.plane_api_url == "http://plane.example.test"
    assert config.plane_api_key == "fake-plane-key-for-tests"
    assert config.plane_workspace_slug == "homelab"
    assert config.plane_project_id == "fake-project-uuid"
    assert config.tracker_api_url == "http://plane.example.test"
    assert config.tracker_api_key == "fake-plane-key-for-tests"
    assert config.tracker_workspace_slug == "homelab"
    assert config.tracker_project_id == "fake-project-uuid"
    assert config.bindings[0].tracker_project_id == "fake-project-uuid"
    assert config.homelab_repo_path == Path("/home/james/homelab")
    assert config.pi_bin == "/usr/local/bin/pi"
    assert config.pi_provider == "zai"
    assert config.pi_model == "glm-5.1:high"
    assert config.poll_interval_ms == 30_000
    assert config.run_timeout_ms == 7_200_000
    assert config.claude_persist_idle_ttl_s == 2_700
    assert config.claude_persist_max_live == 8
    assert config.blocked_reconciler_interval_ms == 1_800_000
    assert config.issue_telegram_notifications_enabled is False
    assert config.lock_path == Path("/home/james/homelab/.symphony.lock")


def test_from_env_loads_tracker_neutral_env_values():
    config = SymphonyConfig.from_env(
        _tracker_env(
            SYMPHONY_TRACKER_FRONTEND_URL="http://tracker.example.test/ui/",
            SYMPHONY_TRACKER_DASHBOARD_URL="http://tracker.example.test/dash/",
        )
    )

    assert config.plane_api_url == "http://tracker.example.test"
    assert config.plane_api_key == "fake-tracker-key-for-tests"
    assert config.plane_workspace_slug == "tracker-workspace"
    assert config.plane_project_id == "fake-tracker-project-uuid"
    assert config.tracker_frontend_url == "http://tracker.example.test/ui"
    assert config.tracker_dashboard_url == "http://tracker.example.test/dash/"
    assert config.homelab_repo_path == Path("/home/james/tracker-repo")
    assert config.bindings[0].tracker_project_id == "fake-tracker-project-uuid"


def test_from_env_prefers_tracker_neutral_env_over_legacy_plane_env():
    config = SymphonyConfig.from_env(
        _env(
            SYMPHONY_TRACKER_API_URL="http://tracker.example.test",
            SYMPHONY_TRACKER_API_KEY="fake-tracker-key-for-tests",
            SYMPHONY_TRACKER_WORKSPACE_SLUG="tracker-workspace",
            SYMPHONY_TRACKER_PROJECT_ID="fake-tracker-project-uuid",
            SYMPHONY_TRACKER_FRONTEND_URL="http://tracker.example.test/ui/",
            SYMPHONY_TRACKER_DASHBOARD_URL="http://tracker.example.test/dash/",
        )
    )

    assert config.plane_api_url == "http://tracker.example.test"
    assert config.plane_api_key == "fake-tracker-key-for-tests"
    assert config.plane_workspace_slug == "tracker-workspace"
    assert config.plane_project_id == "fake-tracker-project-uuid"
    assert config.plane_frontend_url == "http://tracker.example.test/ui"
    assert config.plane_dashboard_url == "http://tracker.example.test/dash/"


def test_from_env_loads_optional_values():
    config = SymphonyConfig.from_env(
        _env(
            SYMPHONY_POLL_INTERVAL_MS="1000",
            SYMPHONY_RUN_TIMEOUT_MS="2000",
            SYMPHONY_CLAUDE_PERSIST_IDLE_TTL_S="1200",
            SYMPHONY_CLAUDE_PERSIST_MAX_LIVE="3",
            SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS="3000",
            SYMPHONY_LOCK_PATH="/run/symphony.lock",
        )
    )

    assert config.poll_interval_ms == 1_000
    assert config.run_timeout_ms == 2_000
    assert config.claude_persist_idle_ttl_s == 1_200
    assert config.claude_persist_max_live == 3
    assert config.blocked_reconciler_interval_ms == 3_000
    assert config.lock_path == Path("/run/symphony.lock")


def test_from_env_loads_issue_telegram_notifications_opt_in():
    config = SymphonyConfig.from_env(_env(SYMPHONY_ISSUE_TELEGRAM_NOTIFICATIONS="true"))

    assert config.issue_telegram_notifications_enabled is True


def test_from_env_loads_pi_provider_override():
    config = SymphonyConfig.from_env(_env(SYMPHONY_PI_PROVIDER="test-provider"))

    assert config.pi_provider == "test-provider"


def test_from_env_loads_pi_model_override():
    config = SymphonyConfig.from_env(_env(SYMPHONY_PI_MODEL="test-model:high"))

    assert config.pi_model == "test-model:high"


def test_repr_and_str_redact_plane_api_key_and_include_pi_fields():
    config = SymphonyConfig.from_env(_env())

    assert "fake-plane-key-for-tests" not in repr(config)
    assert "fake-plane-key-for-tests" not in str(config)
    assert "<redacted>" in repr(config)
    assert "pi_bin='/usr/local/bin/pi'" in repr(config)
    assert "pi_provider='zai'" in repr(config)
    assert "pi_model='glm-5.1:high'" in repr(config)


def test_plane_dashboard_url_defaults_to_empty():
    config = SymphonyConfig.from_env(_env())
    assert config.plane_dashboard_url == ""


def test_plane_dashboard_url_loaded_from_env():
    config = SymphonyConfig.from_env(
        _env(PLANE_DASHBOARD_URL="http://plane.example.test/dash/")
    )
    assert config.plane_dashboard_url == "http://plane.example.test/dash/"


def test_plane_frontend_url_loaded_from_env_and_strips_trailing_slash():
    config = SymphonyConfig.from_env(
        _env(PLANE_FRONTEND_URL="http://10.20.20.16:8000/")
    )
    assert config.plane_frontend_url == "http://10.20.20.16:8000"


def test_issue_url_returns_frontend_url():
    config = SymphonyConfig.from_env(_env())
    url = config.issue_url("abc-123")
    assert (
        url
        == "http://plane.example.test/homelab/projects/fake-project-uuid/issues/abc-123/"
    )


def test_issue_url_returns_empty_for_empty_issue_id():
    config = SymphonyConfig.from_env(_env())
    assert config.issue_url("") == ""


def test_issue_url_strips_api_path_prefix():
    config = SymphonyConfig.from_env(
        _env(PLANE_API_URL="http://plane.example.test/api/v1")
    )
    url = config.issue_url("i-1")
    assert url.startswith("http://plane.example.test/homelab/")
    assert "i-1" in url


def test_issue_url_prefers_frontend_url_over_local_api_url():
    config = SymphonyConfig.from_env(
        _env(
            PLANE_API_URL="http://127.0.0.1:8000",
            PLANE_FRONTEND_URL="http://10.20.20.16:8000",
        )
    )
    assert (
        config.issue_url("i-1")
        == "http://10.20.20.16:8000/homelab/projects/fake-project-uuid/issues/i-1/"
    )


def test_from_env_without_bindings_yml_preserves_single_binding_defaults():
    config = SymphonyConfig.from_env(_env(SYMPHONY_BASE_BRANCH="main"))

    assert len(config.bindings) == 1
    binding = config.bindings[0]
    assert binding.plane_project_id == "fake-project-uuid"
    assert binding.repo_path == Path("/home/james/homelab")
    assert binding.base_branch == "main"
    assert binding.default_agent == "pi"
    assert binding.approval_policy.enabled is False
    assert binding.landing_policy.mode == "local"
    assert binding.tracker_contract.project_id == "fake-project-uuid"


def test_from_env_loads_multi_binding_yaml(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: homelab
    plane_project_id: project-a
    repo_path: /srv/homelab
    base_branch: main
    default_agent: pi
  - name: tools
    plane_project_id: project-b
    repo_path: /srv/tools
    base_branch: develop
    default_agent: claude
    approval:
      enabled: true
    landing:
      mode: local
    tracker_contract:
      project_slug: tools
      state_roles:
        state:todo: Todo
        state:running: Running
        state:in-review: In Review
        state:blocked: Blocked
        state:done: Done
      label_roles:
        mode:plan: plan
        mode:build: build
""".lstrip(),
        encoding="utf-8",
    )

    config = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )

    assert config.plane_api_key == "env-secret"
    assert config.plane_project_id == "project-a"
    assert config.homelab_repo_path == Path("/srv/homelab")
    assert [binding.name for binding in config.bindings] == ["homelab", "tools"]
    assert config.bindings[0].approval_policy.enabled is False
    assert config.bindings[0].landing_policy.mode == "local"
    assert config.bindings[0].tracker == "plane"
    assert config.bindings[1].plane_project_id == "project-b"
    assert config.bindings[1].repo_path == Path("/srv/tools")
    assert config.bindings[1].base_branch == "develop"
    assert config.bindings[1].default_agent == "claude"
    assert config.bindings[1].approval_policy.enabled is True
    assert config.bindings[1].tracker == "plane"
    assert config.bindings[1].tracker_contract.project_id == "project-b"
    assert config.bindings[1].tracker_contract.project_slug == "tools"


def test_bindings_yml_parses_claude_persist_flag(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: claude-local
    plane_project_id: project-a
    repo_path: /srv/claude
    base_branch: main
    default_agent: claude
    tracker: podium
    claude_persist: true
  - name: default-local
    plane_project_id: project-b
    repo_path: /srv/default
    base_branch: main
    default_agent: pi
    tracker: podium
""".lstrip(),
        encoding="utf-8",
    )

    config = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )

    assert config.bindings[0].claude_persist is True
    assert config.bindings[1].claude_persist is False


def test_bindings_yml_parses_auto_close_on_verified_flag(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: patrol-infra
    plane_project_id: project-a
    repo_path: /srv/infra
    base_branch: main
    default_agent: pi
    tracker: podium
    auto_close_on_verified: true
  - name: plain-infra
    plane_project_id: project-b
    repo_path: /srv/plain
    base_branch: main
    default_agent: pi
    tracker: podium
""".lstrip(),
        encoding="utf-8",
    )

    config = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )

    assert config.bindings[0].auto_close_on_verified is True
    assert config.bindings[1].auto_close_on_verified is False


def test_bindings_yml_rejects_auto_close_on_verified_for_coding(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: bad-coding
    plane_project_id: project-a
    repo_path: /srv/code
    base_branch: main
    default_agent: pi
    tracker: podium
    type: coding
    auto_close_on_verified: true
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"bindings\[0\]\.auto_close_on_verified"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


def test_bindings_yml_rejects_non_bool_claude_persist(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: bad
    plane_project_id: project-a
    repo_path: /srv/bad
    base_branch: main
    default_agent: claude
    tracker: podium
    claude_persist: yes-please
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"bindings\[0\]\.claude_persist"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


def test_bindings_yml_accepts_podium_tracker(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: podium-test
    plane_project_id: project-a
    repo_path: /srv/podium
    base_branch: main
    default_agent: pi
    tracker: podium
""".lstrip(),
        encoding="utf-8",
    )

    config = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )

    assert config.bindings[0].tracker == "podium"


def test_bindings_yml_rejects_unknown_tracker(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: bad
    plane_project_id: project-a
    repo_path: /srv/bad
    base_branch: main
    default_agent: pi
    tracker: jira
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="tracker: must be 'plane' or 'podium'"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


def test_bindings_yml_parses_remote_block(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: n8n
    plane_project_id: project-a
    repo_path: /home/itadmin/repo
    base_branch: main
    default_agent: pi
    type: coding
    pi_mode: rpc
    tracker: podium
    remote:
      host: 100.95.224.218
      user: itadmin
      identity: ~/.ssh/id_remote
""".lstrip(),
        encoding="utf-8",
    )

    binding = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    ).bindings[0]

    assert binding.is_remote
    assert binding.remote is not None
    assert binding.remote.host == "100.95.224.218"
    assert binding.remote.user == "itadmin"
    assert binding.remote.identity == "~/.ssh/id_remote"


def test_bindings_yml_without_remote_block_is_local(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: local-test
    plane_project_id: project-a
    repo_path: /srv/local
    base_branch: main
    default_agent: pi
    tracker: podium
""".lstrip(),
        encoding="utf-8",
    )

    binding = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    ).bindings[0]

    assert binding.remote is None
    assert not binding.is_remote


def test_bindings_yml_remote_block_requires_host(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: bad-remote
    plane_project_id: project-a
    repo_path: /srv/bad
    base_branch: main
    default_agent: pi
    tracker: podium
    remote:
      user: itadmin
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="remote.host"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


def _write_remote_binding(
    bindings_path: Path,
    *,
    binding_type: str = "coding",
    pi_mode: str = "rpc",
    default_agent: str = "pi",
    claude_persist: str = "",
) -> None:
    claude_persist_line = (
        f"    claude_persist: {claude_persist}\n" if claude_persist else ""
    )
    bindings_path.write_text(
        f"""
bindings:
  - name: n8n
    plane_project_id: project-a
    repo_path: /home/itadmin/repo
    base_branch: main
    default_agent: {default_agent}
    type: {binding_type}
    pi_mode: {pi_mode}
    tracker: podium
{claude_persist_line}    remote:
      host: 100.95.224.218
      user: itadmin
""".lstrip(),
        encoding="utf-8",
    )


def _load_remote_binding(bindings_path: Path):
    return SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )


def test_remote_binding_with_infra_type_rejected(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path, binding_type="infra")
    with pytest.raises(ConfigError, match="remote bindings require 'coding'"):
        _load_remote_binding(bindings_path)


def test_remote_binding_with_oneshot_pi_mode_rejected(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path, pi_mode="one-shot")
    with pytest.raises(ConfigError, match="remote bindings require 'rpc'"):
        _load_remote_binding(bindings_path)


def test_remote_binding_with_claude_default_agent_parses(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path, default_agent="claude")
    binding = _load_remote_binding(bindings_path).bindings[0]
    assert binding.is_remote
    assert binding.default_agent == "claude"
    assert binding.pi_mode == "rpc"


def test_remote_binding_claude_does_not_require_rpc_pi_mode(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path, default_agent="claude", pi_mode="one-shot")
    binding = _load_remote_binding(bindings_path).bindings[0]
    assert binding.default_agent == "claude"
    assert binding.pi_mode == "one-shot"


def test_remote_binding_coding_rpc_pi_parses(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path)
    binding = _load_remote_binding(bindings_path).bindings[0]
    assert binding.is_remote
    assert binding.binding_type == "coding"
    assert binding.pi_mode == "rpc"
    assert binding.default_agent == "pi"
    assert binding.claude_persist is False


def test_remote_binding_rejects_claude_persist(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path, claude_persist="true")
    with pytest.raises(ConfigError, match=r"claude_persist"):
        _load_remote_binding(bindings_path)


def test_remote_claude_binding_rejects_claude_persist(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(
        bindings_path, default_agent="claude", claude_persist="true"
    )
    with pytest.raises(ConfigError, match=r"claude_persist"):
        _load_remote_binding(bindings_path)


def test_remote_binding_accepts_explicit_false_claude_persist(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    _write_remote_binding(bindings_path, claude_persist="false")
    binding = _load_remote_binding(bindings_path).bindings[0]
    assert binding.claude_persist is False


def test_binding_resolves_agent_label_override():
    binding = SymphonyConfig.from_env(_env(SYMPHONY_DEFAULT_AGENT="pi")).bindings[0]

    assert binding.resolve_agent(()) == "pi"
    assert binding.resolve_agent(("agent:claude",)) == "claude"
    assert binding.resolve_agent(("agent:pi",)) == "pi"


def test_repository_bindings_allow_blank_optional_has_worktree_uuid():
    bindings_path = Path(__file__).resolve().parents[1] / "bindings.yml"

    config = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )

    assert len(config.bindings) >= 1
    for binding in config.bindings:
        role = binding.tracker_contract.optional_label_binding(TrackerRole.HAS_WORKTREE)
        assert role is not None
        assert role.name == "has-worktree"
        adapter = build_adapter(InMemoryTransport(), contract=binding.tracker_contract)
        assert adapter.contract is binding.tracker_contract


def test_bindings_yml_missing_required_field_names_field(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: homelab
    plane_project_id: project-a
    base_branch: main
    default_agent: pi
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"bindings\[0\]\.repo_path is required"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


def test_bindings_yml_rejects_yaml_secrets(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: homelab
    plane_project_id: project-a
    repo_path: /srv/homelab
    base_branch: main
    default_agent: pi
    plane_api_key: should-not-be-read
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="secrets must come from env"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


def test_bindings_yml_rejects_duplicate_project_ids(tmp_path: Path):
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        """
bindings:
  - name: alpha
    plane_project_id: project-x
    repo_path: /srv/alpha
    base_branch: main
    default_agent: pi
  - name: beta
    plane_project_id: project-x
    repo_path: /srv/beta
    base_branch: main
    default_agent: claude
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="duplicate plane_project_id"):
        SymphonyConfig.from_env(
            {
                "PLANE_API_URL": "http://plane.example.test",
                "PLANE_API_KEY": "env-secret",
                "PLANE_WORKSPACE_SLUG": "homelab",
                "PI_BIN": "/usr/local/bin/pi",
                "SYMPHONY_BINDINGS_PATH": str(bindings_path),
            }
        )


# ---- _truthy() N9 dev-review tests ----------------------------------------


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", "ON"])
def test_truthy_accepts_canonical_true_values(raw):
    assert _truthy(raw, default=False) is True


@pytest.mark.parametrize("raw", ["0", "false", "FALSE", "No", "off", "OFF"])
def test_truthy_accepts_canonical_false_values(raw):
    assert _truthy(raw, default=True) is False


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_truthy_falls_back_to_default_for_empty_or_unset(raw):
    assert _truthy(raw, default=True) is True
    assert _truthy(raw, default=False) is False


def test_truthy_unparseable_value_logs_warning_and_returns_default(caplog):
    """N9 dev-review: a typo like APPLY=treu must never silently flip a
    sensitive flag. Behaviour: fall back to default AND log a discoverable
    warning so journalctl shows the bad value."""
    caplog.set_level("WARNING", logger="config")
    result = _truthy("treu", default=False, name="SYMPHONY_BLOCKED_RECONCILER_APPLY")
    assert result is False
    assert any(
        "config_truthy_unparseable" in record.message
        and "SYMPHONY_BLOCKED_RECONCILER_APPLY" in record.message
        and "'treu'" in record.message
        for record in caplog.records
    )


def test_truthy_unparseable_without_name_does_not_log(caplog):
    """If no `name=` is supplied, _truthy stays silent (used by call sites
    that don't want a warning, e.g. ad-hoc parsing in tests)."""
    caplog.set_level("WARNING", logger="config")
    result = _truthy("treu", default=True)
    assert result is True
    assert not any(
        "config_truthy_unparseable" in record.message for record in caplog.records
    )
