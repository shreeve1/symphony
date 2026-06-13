from __future__ import annotations

import pytest

from model_catalog import ModelResolutionError, resolve_model, validate_models


def _catalog(*models: dict[str, object]) -> dict[str, object]:
    return {"models": list(models)}


def test_validate_models_allows_one_default_per_agent() -> None:
    models = validate_models(
        _catalog(
            {
                "id": "gpt-5.5",
                "agent": "pi",
                "provider": "openai-codex",
                "default": True,
            },
            {"id": "claude-opus-4-8", "agent": "claude", "default": True},
        )
    )

    assert [model["id"] for model in models if model.get("default")] == [
        "gpt-5.5",
        "claude-opus-4-8",
    ]


@pytest.mark.parametrize(
    "agent, first, second",
    [("pi", "gpt-a", "gpt-b"), ("claude", "claude-a", "claude-b")],
)
def test_validate_models_rejects_duplicate_defaults_per_agent(
    agent: str, first: str, second: str
) -> None:
    provider = {"provider": "openai-codex"} if agent == "pi" else {}

    with pytest.raises(ValueError) as excinfo:
        validate_models(
            _catalog(
                {"id": first, "agent": agent, "default": True, **provider},
                {"id": second, "agent": agent, "default": True, **provider},
            )
        )

    message = str(excinfo.value)
    assert agent in message
    assert first in message
    assert second in message


def test_validate_models_parses_efforts() -> None:
    models = validate_models(
        _catalog(
            {
                "id": "gpt-5.5",
                "agent": "pi",
                "provider": "openai-codex",
                "efforts": ["none", "low", "medium", "high", "xhigh"],
            },
        )
    )

    assert models[0]["efforts"] == ["none", "low", "medium", "high", "xhigh"]


def test_validate_models_efforts_optional() -> None:
    models = validate_models(
        _catalog({"id": "gpt-5.5", "agent": "pi", "provider": "openai-codex"})
    )

    assert "efforts" not in models[0]


@pytest.mark.parametrize("bad", [[], "high", [""], [42]])
def test_validate_models_rejects_bad_efforts(bad: object) -> None:
    with pytest.raises(ValueError, match="efforts"):
        validate_models(
            _catalog(
                {
                    "id": "gpt-5.5",
                    "agent": "pi",
                    "provider": "openai-codex",
                    "efforts": bad,
                }
            )
        )


def test_resolve_model_selects_default_for_agent() -> None:
    models = validate_models(
        _catalog(
            {
                "id": "gpt-5.5",
                "agent": "pi",
                "provider": "openai-codex",
                "default": True,
            },
            {"id": "claude-opus-4-8", "agent": "claude", "default": True},
        )
    )

    assert resolve_model(None, models, agent="pi")["id"] == "gpt-5.5"
    assert resolve_model(None, models, agent="claude")["id"] == "claude-opus-4-8"


def test_resolve_model_missing_agent_default_names_agent() -> None:
    models = validate_models(
        _catalog(
            {
                "id": "gpt-5.5",
                "agent": "pi",
                "provider": "openai-codex",
                "default": True,
            },
            {"id": "claude-opus-4-8", "agent": "claude"},
        )
    )

    with pytest.raises(ModelResolutionError, match="agent `claude`"):
        resolve_model(None, models, agent="claude")


def test_resolve_model_explicit_preference_ignores_agent_default() -> None:
    models = validate_models(
        _catalog(
            {
                "id": "gpt-5.5",
                "agent": "pi",
                "provider": "openai-codex",
                "default": True,
            },
            {"id": "claude-opus-4-8", "agent": "claude", "default": True},
        )
    )

    assert (
        resolve_model("claude-opus-4-8", models, agent="pi")["id"] == "claude-opus-4-8"
    )
    with pytest.raises(ModelResolutionError, match="missing-model"):
        resolve_model("missing-model", models, agent="claude")
