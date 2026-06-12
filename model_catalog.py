"""Git-tracked model catalog (`models.yml`) shared by Podium and the scheduler.

The catalog is the single source of truth for which models can be dispatched.
`/api/bindings/{name}/options` feeds the new-issue Model dropdown from it, and
the scheduler resolves `issue.preferred_model` against it at dispatch time.
Exactly one entry carries `default: true`; that entry is used when an issue
has no `preferred_model`. Unknown models fail dispatch loudly rather than
falling back silently.
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

    seen: set[str] = set()
    defaults: list[str] = []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(models):
        if not isinstance(item, dict):
            raise ValueError(f"models[{index}] must be a mapping")
        model_id = item.get("id")
        agent = item.get("agent")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"models[{index}].id is required")
        if model_id in seen:
            raise ValueError(f"duplicate model id: {model_id}")
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
        default = item.get("default")
        if default is not None:
            if not isinstance(default, bool):
                raise ValueError(f"models[{index}].default must be a boolean")
            if default:
                entry["default"] = True
                defaults.append(model_id)
        result.append(entry)
        seen.add(model_id)
    if len(defaults) != 1:
        raise ValueError(
            f"exactly one model must set default: true (found {len(defaults)})"
        )
    return result


def load_models(path: Path | None = None) -> list[dict[str, Any]]:
    catalog_path = path or MODELS_PATH
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    return validate_models(data)


def resolve_model(
    preferred_model: str | None, models: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resolve an issue's preferred model (or the catalog default) to an entry.

    Raises ModelResolutionError for models absent from the catalog — dispatch
    must fail loudly instead of silently running a different model.
    """
    if preferred_model:
        for entry in models:
            if entry["id"] == preferred_model:
                return entry
        raise ModelResolutionError(
            f"model {preferred_model!r} is not in models.yml; "
            "add it to the catalog or clear preferred_model"
        )
    for entry in models:
        if entry.get("default"):
            return entry
    raise ModelResolutionError("models.yml has no default: true entry")
