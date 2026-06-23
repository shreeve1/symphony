"""Git-tracked model catalog (`models.yml`) shared by Podium and the scheduler.

The catalog is the single source of truth for which models can be dispatched.
`/api/bindings/{name}/options` feeds the new-issue Model dropdown from it, and
the scheduler resolves `issue.preferred_model` against it at dispatch time.
Each agent may carry at most one `default: true`; that per-agent entry is used
when an issue has no `preferred_model`. Unknown models fail dispatch loudly
rather than falling back silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

KNOWN_AGENTS = ["pi", "claude"]

MODELS_PATH = Path(__file__).resolve().parent / "models.yml"


class ModelResolutionError(ValueError):
    """Raised when a preferred model cannot be resolved against the catalog."""


def validate_models(data: Any) -> list[dict[str, Any]]:
    """Validate the model catalog mapping loaded from models.yml."""
    if not isinstance(data, dict):
        raise ValueError("models.yml must contain a mapping")
    models = data.get("models") or []
    if not isinstance(models, list):
        raise ValueError("models must be a list")

    seen: set[tuple[str, str, str]] = set()
    defaults_by_agent: dict[str, str] = {}
    result: list[dict[str, Any]] = []
    for index, item in enumerate(models):
        if not isinstance(item, dict):
            raise ValueError(f"models[{index}] must be a mapping")
        model_id = item.get("id")
        agent = item.get("agent")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"models[{index}].id is required")
        if agent not in KNOWN_AGENTS:
            raise ValueError(f"models[{index}].agent must be one of {KNOWN_AGENTS}")

        entry: dict[str, Any] = {"id": model_id, "agent": str(agent)}
        for key in ("provider", "label"):
            value = item.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"models[{index}].{key} must be a string")
                entry[key] = value
        if agent == "pi" and not entry.get("provider"):
            raise ValueError(f"models[{index}].provider is required for pi models")
        identity = (str(agent), str(entry.get("provider", "")), model_id)
        if identity in seen:
            raise ValueError(f"duplicate model entry: {model_id}")
        efforts = item.get("efforts")
        if efforts is not None:
            if not isinstance(efforts, list) or not efforts:
                raise ValueError(f"models[{index}].efforts must be a non-empty list")
            cleaned_efforts: list[str] = []
            for effort in efforts:
                if not isinstance(effort, str) or not effort.strip():
                    raise ValueError(
                        f"models[{index}].efforts entries must be non-empty strings"
                    )
                cleaned_efforts.append(effort)
            entry["efforts"] = cleaned_efforts
        default = item.get("default")
        if default is not None:
            if not isinstance(default, bool):
                raise ValueError(f"models[{index}].default must be a boolean")
            if default:
                entry["default"] = True
                previous_default = defaults_by_agent.get(str(agent))
                if previous_default is not None:
                    raise ValueError(
                        f"multiple default: true entries for agent `{agent}`: "
                        f"`{previous_default}` and `{model_id}`"
                    )
                defaults_by_agent[str(agent)] = model_id
        result.append(entry)
        seen.add(identity)
    return result


def load_models(path: Path | None = None) -> list[dict[str, Any]]:
    catalog_path = path or MODELS_PATH
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    return validate_models(data)


def resolve_model(
    preferred_model: str | None, models: list[dict[str, Any]], *, agent: str
) -> dict[str, Any]:
    """Resolve an issue's preferred model (or the catalog default) to an entry.

    Raises ModelResolutionError for models absent from the catalog — dispatch
    must fail loudly instead of silently running a different model. When a
    provider exposes the same id as another agent/provider, `preferred_model`
    may be either `id` (if unique for the resolved agent) or `provider/id`.
    """
    if preferred_model:
        matches = [entry for entry in models if entry["id"] == preferred_model]
        if not matches:
            wanted_provider, _, wanted_id = preferred_model.partition("/")
            if wanted_id:
                matches = [
                    entry
                    for entry in models
                    if entry["id"] == wanted_id
                    and entry.get("provider") == wanted_provider
                ]
        agent_matches = [entry for entry in matches if entry["agent"] == agent]
        if len(agent_matches) == 1:
            return agent_matches[0]
        if len(agent_matches) > 1:
            raise ModelResolutionError(
                f"model {preferred_model!r} is ambiguous for agent `{agent}`; "
                "use provider/id"
            )
        if len(matches) == 1:
            return matches[0]
        raise ModelResolutionError(
            f"model {preferred_model!r} is not in models.yml for agent `{agent}`; "
            "add it to the catalog or clear preferred_model"
        )
    for entry in models:
        if entry.get("default") and entry["agent"] == agent:
            return entry
    raise ModelResolutionError(
        f"models.yml has no default: true entry for agent `{agent}`"
    )
