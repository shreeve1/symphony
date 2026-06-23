from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

main = cast(Any, import_module("web.api.main"))
_skills = cast(Any, import_module("web.cli.podium_skills"))

SKILLS_PATH = Path(".claude/skills/symphony-skills/SKILL.md")
MODELS_SKILL_PATH = Path(".claude/skills/symphony-models/SKILL.md")
MODELS_PATH = Path("models.yml")
CHECKPOINTED_EXPLORATION_SKILL_PATH = Path(
    ".claude/skills/checkpointed-exploration/SKILL.md"
)


def test_symphony_skills_documents_dry_run_then_live_refresh() -> None:
    text = SKILLS_PATH.read_text(encoding="utf-8")

    assert "python -m web.cli.podium skills refresh --dry-run" in text
    assert "python -m web.cli.podium skills refresh" in text
    assert "GET /api/skills" in text
    assert "No service restart" in text
    assert "No Plane API calls" in text
    assert "symphony-host.env" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text


def test_checkpointed_exploration_skill_is_catalog_scannable() -> None:
    records = _skills.scan_skills(Path(".claude/skills"))
    record_by_name = {record.name: record for record in records}
    text = CHECKPOINTED_EXPLORATION_SKILL_PATH.read_text(encoding="utf-8")

    assert "checkpointed-exploration" in record_by_name
    assert "bounded reviewable checkpoints" in record_by_name[
        "checkpointed-exploration"
    ].description
    assert "SYMPHONY_QUESTION_BEGIN" in text
    assert "Do not emit `SYMPHONY_RESULT: done`" in text


def test_symphony_models_documents_list_add_remove_and_shared_validator() -> None:
    text = MODELS_SKILL_PATH.read_text(encoding="utf-8")

    assert "models.yml" in text
    assert "_load_models" in text
    assert "_validate_models" in text
    assert "agent` must be `pi` or `claude`" in text
    assert "id` must be unique" in text
    assert "default: true" in text
    assert "blocked" in text
    assert "No service restart" in text
    assert "No Plane API calls" in text
    assert "symphony-host.env" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text


def test_models_catalog_is_loadable_by_options_validator() -> None:
    loaded = main._load_models(MODELS_PATH)

    assert {item["id"] for item in loaded} >= {
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "gpt-5.3-codex-spark",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.5",
    }
    assert all(item["agent"] in {"pi", "claude"} for item in loaded)


def test_symphony_models_edit_round_trip_uses_shared_validator(tmp_path: Path) -> None:
    catalog = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8"))
    catalog["models"].append(
        {
            "id": "claude-example-model",
            "agent": "claude",
            "label": "Example Model",
        }
    )
    edited = tmp_path / "models.yml"
    edited.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")

    loaded = main._load_models(edited)

    assert any(item["id"] == "claude-example-model" for item in loaded)


@pytest.mark.parametrize(
    "catalog, message",
    [
        ({"models": [{"id": "bad-agent", "agent": "bad"}]}, "agent must be one of"),
        (
            {
                "models": [
                    {"id": "duplicate", "agent": "claude"},
                    {"id": "duplicate", "agent": "claude"},
                ]
            },
            "duplicate model entry",
        ),
    ],
)
def test_shared_models_validator_rejects_bad_agent_and_duplicate_id(
    catalog: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        main._validate_models(catalog)
