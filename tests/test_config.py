from pathlib import Path

import pytest

from config import SymphonyConfig


def _env(**overrides):
    env = {
        "PLANE_API_URL": "http://plane.example.test",
        "PLANE_API_KEY": "fake-plane-key-for-tests",
        "PLANE_WORKSPACE_SLUG": "homelab",
        "PLANE_PROJECT_ID": "fake-project-uuid",
        "HOMELAB_REPO_PATH": "/home/james/homelab",
        "OPENCODE_BIN": "/usr/local/bin/opencode",
    }
    env.update(overrides)
    return env


def test_from_env_lists_all_missing_required_vars():
    with pytest.raises(EnvironmentError) as exc:
        SymphonyConfig.from_env({})

    message = str(exc.value)
    assert "PLANE_API_URL" in message
    assert "PLANE_API_KEY" in message
    assert "PLANE_WORKSPACE_SLUG" in message
    assert "PLANE_PROJECT_ID" in message
    assert "HOMELAB_REPO_PATH" in message
    assert "OPENCODE_BIN" in message


def test_from_env_loads_required_values_with_optional_defaults():
    config = SymphonyConfig.from_env(_env())

    assert config.plane_api_url == "http://plane.example.test"
    assert config.plane_api_key == "fake-plane-key-for-tests"
    assert config.plane_workspace_slug == "homelab"
    assert config.plane_project_id == "fake-project-uuid"
    assert config.homelab_repo_path == Path("/home/james/homelab")
    assert config.opencode_bin == "/usr/local/bin/opencode"
    assert config.opencode_agent == "build"
    assert config.opencode_model is None
    assert config.poll_interval_ms == 30_000
    assert config.run_timeout_ms == 1_800_000
    assert config.lock_path == Path("/home/james/homelab/.symphony.lock")


def test_from_env_loads_optional_values():
    config = SymphonyConfig.from_env(
        _env(
            SYMPHONY_POLL_INTERVAL_MS="1000",
            SYMPHONY_RUN_TIMEOUT_MS="2000",
            SYMPHONY_LOCK_PATH="/run/symphony.lock",
        )
    )

    assert config.poll_interval_ms == 1_000
    assert config.run_timeout_ms == 2_000
    assert config.lock_path == Path("/run/symphony.lock")


def test_from_env_loads_opencode_agent_override():
    config = SymphonyConfig.from_env(_env(SYMPHONY_OPENCODE_AGENT="plan"))

    assert config.opencode_agent == "plan"


def test_from_env_loads_opencode_model_override():
    config = SymphonyConfig.from_env(
        _env(SYMPHONY_OPENCODE_MODEL="zai-coding-plan/glm-5.1")
    )

    assert config.opencode_model == "zai-coding-plan/glm-5.1"


def test_repr_and_str_redact_plane_api_key():
    config = SymphonyConfig.from_env(_env())

    assert "fake-plane-key-for-tests" not in repr(config)
    assert "fake-plane-key-for-tests" not in str(config)
    assert "<redacted>" in repr(config)
