from pathlib import Path

import pytest

from config import SymphonyConfig, _truthy


def _env(**overrides):
    env = {
        "PLANE_API_URL": "http://plane.example.test",
        "PLANE_API_KEY": "fake-plane-key-for-tests",
        "PLANE_WORKSPACE_SLUG": "homelab",
        "PLANE_PROJECT_ID": "fake-project-uuid",
        "HOMELAB_REPO_PATH": "/home/james/homelab",
        "PI_BIN": "/usr/local/bin/pi",
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
    assert "PI_BIN" in message
    assert "OPEN" + "CODE_BIN" not in message


def test_from_env_loads_required_values_with_optional_defaults():
    config = SymphonyConfig.from_env(_env())

    assert config.plane_api_url == "http://plane.example.test"
    assert config.plane_api_key == "fake-plane-key-for-tests"
    assert config.plane_workspace_slug == "homelab"
    assert config.plane_project_id == "fake-project-uuid"
    assert config.homelab_repo_path == Path("/home/james/homelab")
    assert config.pi_bin == "/usr/local/bin/pi"
    assert config.pi_provider == "zai"
    assert config.pi_model == "glm-5.1:high"
    assert config.poll_interval_ms == 30_000
    assert config.run_timeout_ms == 1_800_000
    assert config.blocked_reconciler_interval_ms == 1_800_000
    assert config.lock_path == Path("/home/james/homelab/.symphony.lock")


def test_from_env_loads_optional_values():
    config = SymphonyConfig.from_env(
        _env(
            SYMPHONY_POLL_INTERVAL_MS="1000",
            SYMPHONY_RUN_TIMEOUT_MS="2000",
            SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS="3000",
            SYMPHONY_LOCK_PATH="/run/symphony.lock",
        )
    )

    assert config.poll_interval_ms == 1_000
    assert config.run_timeout_ms == 2_000
    assert config.blocked_reconciler_interval_ms == 3_000
    assert config.lock_path == Path("/run/symphony.lock")


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
    config = SymphonyConfig.from_env(_env(PLANE_DASHBOARD_URL="http://plane.example.test/dash/"))
    assert config.plane_dashboard_url == "http://plane.example.test/dash/"


def test_plane_frontend_url_loaded_from_env_and_strips_trailing_slash():
    config = SymphonyConfig.from_env(_env(PLANE_FRONTEND_URL="http://10.20.20.16:8000/"))
    assert config.plane_frontend_url == "http://10.20.20.16:8000"


def test_issue_url_returns_frontend_url():
    config = SymphonyConfig.from_env(_env())
    url = config.issue_url("abc-123")
    assert url == "http://plane.example.test/homelab/projects/fake-project-uuid/issues/abc-123/"


def test_issue_url_returns_empty_for_empty_issue_id():
    config = SymphonyConfig.from_env(_env())
    assert config.issue_url("") == ""


def test_issue_url_strips_api_path_prefix():
    config = SymphonyConfig.from_env(_env(PLANE_API_URL="http://plane.example.test/api/v1"))
    url = config.issue_url("i-1")
    assert url.startswith("http://plane.example.test/homelab/")
    assert "i-1" in url


def test_issue_url_prefers_frontend_url_over_local_api_url():
    config = SymphonyConfig.from_env(_env(
        PLANE_API_URL="http://127.0.0.1:8000",
        PLANE_FRONTEND_URL="http://10.20.20.16:8000",
    ))
    assert config.issue_url("i-1") == "http://10.20.20.16:8000/homelab/projects/fake-project-uuid/issues/i-1/"


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
