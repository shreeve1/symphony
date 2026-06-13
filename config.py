"""Environment and project-binding configuration for the Symphony service."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml

from tracker_contract import (
    DEFAULT_CONTRACT,
    PlaneUserMapping,
    RoleBinding,
    TrackerContract,
    TrackerRole,
)


LOGGER = logging.getLogger(__name__)


_REQUIRED_ENV = (
    "PLANE_API_URL",
    "PLANE_API_KEY",
    "PLANE_WORKSPACE_SLUG",
    "PLANE_PROJECT_ID",
    "HOMELAB_REPO_PATH",
    "PI_BIN",
)
_BINDINGS_ENV = (
    "PLANE_API_URL",
    "PLANE_API_KEY",
    "PLANE_WORKSPACE_SLUG",
    "PI_BIN",
)
_SECRET_YAML_KEYS = {"plane_api_key", "api_key", "telegram_bot_token", "token", "secret"}


class ConfigError(ValueError):
    """Raised when bindings.yml has invalid Symphony configuration."""


@dataclass(frozen=True)
class ApprovalPolicy:
    """Per-binding approval gate policy. Off unless bindings.yml opts in."""

    enabled: bool = False


@dataclass(frozen=True)
class LandingPolicy:
    """Per-binding landing policy. Local landing is the safe default."""

    mode: str = "local"


@dataclass(frozen=True)
class ProjectBinding:
    """One Plane project ↔ repository binding."""

    name: str
    plane_project_id: str
    repo_path: Path
    base_branch: str
    tracker_contract: TrackerContract
    default_agent: str = "pi"
    binding_type: str = "infra"
    tracker: Literal["plane", "podium"] = "plane"
    pi_mode: Literal["one-shot", "rpc"] = "one-shot"
    approval_policy: ApprovalPolicy = field(default_factory=ApprovalPolicy)
    landing_policy: LandingPolicy = field(default_factory=LandingPolicy)

    def resolve_agent(self, labels: Iterable[str] = ()) -> str:
        """Resolve default agent with optional `agent:pi` / `agent:claude` override."""

        label_set = set(labels)
        if "agent:claude" in label_set:
            return "claude"
        if "agent:pi" in label_set:
            return "pi"
        return self.default_agent


def _truthy(value: str | None, *, default: bool, name: str = "") -> bool:
    """Parse an env-style boolean.

    Accepts ``1/true/yes/on`` (case-insensitive) as true and ``0/false/no/off``
    as false. Empty or unset → ``default``. Any other value also falls back
    to ``default`` so a typo can never silently flip a sensitive flag like
    ``SYMPHONY_BLOCKED_RECONCILER_APPLY``.

    When ``name`` is supplied and the value is unparseable (not empty, not in
    either truthy/falsy set), a warning is logged so an operator typo like
    ``APPLY=treu`` is discoverable in journalctl instead of silently keeping
    the default. The N9 dev-review fix: matches the safe-default behaviour
    with operator visibility.
    """

    if value is None:
        return default
    normalised = value.strip().lower()
    if not normalised:
        return default
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off"}:
        return False
    if name:
        LOGGER.warning(
            "config_truthy_unparseable name=%s value=%r default=%s",
            name, value, default,
        )
    return default


@dataclass(frozen=True)
class SymphonyConfig:
    """Runtime config loaded from environment variables and optional bindings.yml."""

    plane_api_url: str
    plane_api_key: str = field(repr=False)
    plane_workspace_slug: str
    plane_project_id: str
    homelab_repo_path: Path
    pi_bin: str
    pi_provider: str = "zai"
    pi_model: str = "glm-5.1:high"
    poll_interval_ms: int = 30_000
    run_timeout_ms: int = 3_600_000
    run_cap: int = 2
    lock_path: Path | None = None
    telegram_bot_token: str | None = field(default=None, repr=False)
    telegram_chat_id: str | None = None
    plane_frontend_url: str = ""
    plane_dashboard_url: str = ""
    worktrees_root: Path | None = None
    blocked_reconciler_enabled: bool = True
    blocked_reconciler_apply: bool = False
    blocked_reconciler_interval_ms: int = 1_800_000
    base_branch: str = "HEAD"
    bindings: tuple[ProjectBinding, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        repo_path = Path(self.homelab_repo_path)
        object.__setattr__(self, "homelab_repo_path", repo_path)
        if self.lock_path is None:
            object.__setattr__(self, "lock_path", repo_path / ".symphony.lock")
        if self.worktrees_root is None:
            object.__setattr__(
                self,
                "worktrees_root",
                repo_path.parent / f".{repo_path.name}-symphony-worktrees",
            )
        if not self.bindings:
            binding = ProjectBinding(
                name="default",
                plane_project_id=self.plane_project_id,
                repo_path=repo_path,
                base_branch=self.base_branch,
                default_agent="pi",
                tracker_contract=replace(
                    DEFAULT_CONTRACT,
                    workspace_slug=self.plane_workspace_slug,
                    project_id=self.plane_project_id,
                ),
            )
            object.__setattr__(self, "bindings", (binding,))

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "SymphonyConfig":
        source = os.environ if env is None else env
        bindings_path = Path(source.get("SYMPHONY_BINDINGS_PATH", "bindings.yml"))
        use_bindings = bindings_path.is_file()
        required = _BINDINGS_ENV if use_bindings else _REQUIRED_ENV
        missing = [name for name in required if not source.get(name)]
        if missing:
            raise EnvironmentError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        bindings = (
            _load_bindings_yml(bindings_path, workspace_slug=source["PLANE_WORKSPACE_SLUG"])
            if use_bindings
            else (
                _binding_from_env(source),
            )
        )
        first = bindings[0]

        return cls(
            plane_api_url=source["PLANE_API_URL"].rstrip("/"),
            plane_api_key=source["PLANE_API_KEY"],
            plane_workspace_slug=source["PLANE_WORKSPACE_SLUG"],
            plane_project_id=first.plane_project_id,
            homelab_repo_path=first.repo_path,
            pi_bin=source["PI_BIN"],
            pi_provider=source.get("SYMPHONY_PI_PROVIDER", "zai"),
            pi_model=source.get("SYMPHONY_PI_MODEL", "glm-5.1:high"),
            poll_interval_ms=int(source.get("SYMPHONY_POLL_INTERVAL_MS", "30000")),
            run_timeout_ms=int(source.get("SYMPHONY_RUN_TIMEOUT_MS", "3600000")),
            run_cap=int(source.get("SYMPHONY_RUN_CAP", "2")),
            lock_path=Path(source["SYMPHONY_LOCK_PATH"]) if source.get("SYMPHONY_LOCK_PATH") else None,
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=source.get("TELEGRAM_CHAT_ID") or source.get("TELEGRAM_HOME_CHANNEL"),
            plane_frontend_url=source.get("PLANE_FRONTEND_URL", "").rstrip("/"),
            plane_dashboard_url=source.get("PLANE_DASHBOARD_URL", ""),
            worktrees_root=(
                Path(source["SYMPHONY_WORKTREES_ROOT"])
                if source.get("SYMPHONY_WORKTREES_ROOT")
                else None
            ),
            blocked_reconciler_enabled=_truthy(
                source.get("SYMPHONY_BLOCKED_RECONCILER_ENABLED"),
                default=True,
                name="SYMPHONY_BLOCKED_RECONCILER_ENABLED",
            ),
            blocked_reconciler_apply=_truthy(
                source.get("SYMPHONY_BLOCKED_RECONCILER_APPLY"),
                default=False,
                name="SYMPHONY_BLOCKED_RECONCILER_APPLY",
            ),
            blocked_reconciler_interval_ms=int(
                source.get("SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS", "1800000")
            ),
            base_branch=first.base_branch,
            bindings=bindings,
        )

    def for_binding(self, binding: ProjectBinding) -> "SymphonyConfig":
        """Return config scoped to one project binding."""

        return replace(
            self,
            plane_project_id=binding.plane_project_id,
            homelab_repo_path=binding.repo_path,
            base_branch=binding.base_branch,
            bindings=(binding,),
            lock_path=binding.repo_path / ".symphony.lock",
            worktrees_root=binding.repo_path.parent / f".{binding.repo_path.name}-symphony-worktrees",
            run_cap=self.run_cap,
        )

    def issue_url(self, issue_id: str) -> str:
        """Return the Plane frontend URL for a specific issue."""
        if not issue_id:
            return ""
        from urllib.parse import urlparse
        if self.plane_frontend_url:
            base = self.plane_frontend_url
        else:
            parsed = urlparse(self.plane_api_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
        return (
            f"{base}/{self.plane_workspace_slug}/projects/"
            f"{self.plane_project_id}/issues/{issue_id}/"
        )

    def __repr__(self) -> str:
        telegram_chat_id = "<redacted>" if self.telegram_chat_id else None
        return (
            "SymphonyConfig("
            f"plane_api_url={self.plane_api_url!r}, "
            "plane_api_key='<redacted>', "
            f"plane_workspace_slug={self.plane_workspace_slug!r}, "
            f"plane_project_id={self.plane_project_id!r}, "
            f"homelab_repo_path={self.homelab_repo_path!r}, "
            f"pi_bin={self.pi_bin!r}, "
            f"pi_provider={self.pi_provider!r}, "
            f"pi_model={self.pi_model!r}, "
            f"poll_interval_ms={self.poll_interval_ms!r}, "
            f"run_timeout_ms={self.run_timeout_ms!r}, "
            f"run_cap={self.run_cap!r}, "
            f"lock_path={self.lock_path!r}, "
            f"telegram_chat_id={telegram_chat_id!r}, "
            f"plane_frontend_url={self.plane_frontend_url!r}, "
            f"plane_dashboard_url={self.plane_dashboard_url!r}, "
            f"base_branch={self.base_branch!r}, "
            f"blocked_reconciler_enabled={self.blocked_reconciler_enabled!r}, "
            f"blocked_reconciler_apply={self.blocked_reconciler_apply!r}, "
            f"blocked_reconciler_interval_ms={self.blocked_reconciler_interval_ms!r})"
        )

    __str__ = __repr__


def _binding_from_env(source: os._Environ[str] | dict[str, str]) -> ProjectBinding:
    default_agent = source.get("SYMPHONY_DEFAULT_AGENT", "pi")
    _validate_agent(default_agent, "SYMPHONY_DEFAULT_AGENT")
    project_id = source["PLANE_PROJECT_ID"]
    return ProjectBinding(
        name=source.get("SYMPHONY_BINDING_NAME", "default"),
        plane_project_id=project_id,
        repo_path=Path(source["HOMELAB_REPO_PATH"]),
        base_branch=source.get("SYMPHONY_BASE_BRANCH", "HEAD"),
        default_agent=default_agent,
        tracker_contract=replace(
            DEFAULT_CONTRACT,
            workspace_slug=source["PLANE_WORKSPACE_SLUG"],
            project_id=project_id,
        ),
        approval_policy=ApprovalPolicy(
            enabled=_truthy(
                source.get("SYMPHONY_APPROVAL_GATE_ENABLED"),
                default=False,
                name="SYMPHONY_APPROVAL_GATE_ENABLED",
            )
        ),
        landing_policy=LandingPolicy(source.get("SYMPHONY_LANDING_MODE", "local")),
    )


def _load_bindings_yml(path: Path, *, workspace_slug: str) -> tuple[ProjectBinding, ...]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected mapping with bindings list")
    _reject_yaml_secrets(raw, "bindings.yml")
    bindings_raw = raw.get("bindings")
    if not isinstance(bindings_raw, list) or not bindings_raw:
        raise ConfigError(f"{path}: bindings must be a non-empty list")
    bindings: list[ProjectBinding] = []
    for idx, item in enumerate(bindings_raw):
        prefix = f"bindings[{idx}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{prefix}: expected mapping")
        bindings.append(_binding_from_mapping(item, prefix=prefix, workspace_slug=workspace_slug))
    seen_project_ids: set[str] = set()
    for idx, binding in enumerate(bindings):
        if binding.plane_project_id in seen_project_ids:
            raise ConfigError(
                f"bindings[{idx}]: duplicate plane_project_id "
                f"'{binding.plane_project_id}' — each binding must target a "
                f"distinct Plane project"
            )
        seen_project_ids.add(binding.plane_project_id)
    return tuple(bindings)


def _binding_from_mapping(raw: dict[str, Any], *, prefix: str, workspace_slug: str) -> ProjectBinding:
    _reject_yaml_secrets(raw, prefix)
    plane_project_id = _required_string(raw, "plane_project_id", prefix)
    repo_path = Path(_required_string(raw, "repo_path", prefix))
    base_branch = _required_string(raw, "base_branch", prefix)
    default_agent = _required_string(raw, "default_agent", prefix)
    _validate_agent(default_agent, f"{prefix}.default_agent")
    approval = raw.get("approval") or {}
    if not isinstance(approval, dict):
        raise ConfigError(f"{prefix}.approval: expected mapping")
    landing = raw.get("landing") or {}
    if not isinstance(landing, dict):
        raise ConfigError(f"{prefix}.landing: expected mapping")
    contract_raw = raw.get("tracker_contract", raw.get("contract"))
    contract = _contract_from_mapping(
        contract_raw,
        prefix=f"{prefix}.tracker_contract",
        workspace_slug=workspace_slug,
        plane_project_id=plane_project_id,
    )
    binding_type = str(raw.get("type", "infra") or "infra")
    if binding_type not in {"infra", "coding"}:
        raise ConfigError(f"{prefix}.type: must be 'infra' or 'coding', got '{binding_type}'")
    tracker_raw = str(raw.get("tracker", "plane") or "plane")
    if tracker_raw not in {"plane", "podium"}:
        raise ConfigError(f"{prefix}.tracker: must be 'plane' or 'podium', got '{tracker_raw}'")
    tracker: Literal["plane", "podium"] = "podium" if tracker_raw == "podium" else "plane"
    pi_mode_raw = str(raw.get("pi_mode", "one-shot") or "one-shot")
    if pi_mode_raw not in {"one-shot", "rpc"}:
        raise ConfigError(f"{prefix}.pi_mode: must be 'one-shot' or 'rpc', got '{pi_mode_raw}'")
    pi_mode: Literal["one-shot", "rpc"] = "rpc" if pi_mode_raw == "rpc" else "one-shot"
    return ProjectBinding(
        name=str(raw.get("name") or plane_project_id),
        plane_project_id=plane_project_id,
        repo_path=repo_path,
        base_branch=base_branch,
        default_agent=default_agent,
        binding_type=binding_type,
        tracker=tracker,
        pi_mode=pi_mode,
        tracker_contract=contract,
        approval_policy=ApprovalPolicy(enabled=bool(approval.get("enabled", False))),
        landing_policy=LandingPolicy(mode=str(landing.get("mode", "local"))),
    )


def _contract_from_mapping(
    raw: Any,
    *,
    prefix: str,
    workspace_slug: str,
    plane_project_id: str,
) -> TrackerContract:
    if raw is None:
        return replace(
            DEFAULT_CONTRACT,
            workspace_slug=workspace_slug,
            project_id=plane_project_id,
        )
    if not isinstance(raw, dict):
        raise ConfigError(f"{prefix}: expected mapping")
    _reject_yaml_secrets(raw, prefix)
    contract = replace(
        DEFAULT_CONTRACT,
        workspace_slug=str(raw.get("workspace_slug") or workspace_slug),
        project_slug=str(raw.get("project_slug") or DEFAULT_CONTRACT.project_slug),
        project_id=str(raw.get("project_id") or plane_project_id),
        state_roles=_role_bindings(
            raw.get("state_roles"),
            default=DEFAULT_CONTRACT.state_roles,
            prefix=f"{prefix}.state_roles",
        ),
        label_roles=_role_bindings(
            raw.get("label_roles"),
            default=DEFAULT_CONTRACT.label_roles,
            prefix=f"{prefix}.label_roles",
        ),
        extra_label_ids=dict(raw.get("extra_label_ids") or DEFAULT_CONTRACT.extra_label_ids),
        users=_users(raw.get("users"), prefix=f"{prefix}.users"),
    )
    errors = contract.validate_shape()
    if errors:
        raise ConfigError(f"{prefix}: " + "; ".join(errors))
    return contract


def _role_bindings(raw: Any, *, default: dict[TrackerRole, RoleBinding], prefix: str) -> dict[TrackerRole, RoleBinding]:
    if raw is None:
        return dict(default)
    if not isinstance(raw, dict):
        raise ConfigError(f"{prefix}: expected mapping")
    parsed: dict[TrackerRole, RoleBinding] = {}
    for key, value in raw.items():
        try:
            role = TrackerRole(str(key))
        except ValueError as exc:
            raise ConfigError(f"{prefix}.{key}: unknown tracker role") from exc
        parsed[role] = _role_binding(value, prefix=f"{prefix}.{key}")
    return parsed


def _role_binding(raw: Any, *, prefix: str) -> RoleBinding:
    if isinstance(raw, str):
        return RoleBinding(raw)
    if not isinstance(raw, dict):
        raise ConfigError(f"{prefix}: expected string or mapping")
    name = _required_string(raw, "name", prefix)
    return RoleBinding(name=name, uuid=str(raw.get("uuid") or ""))


def _users(raw: Any, *, prefix: str) -> tuple[PlaneUserMapping, ...]:
    if raw is None:
        return DEFAULT_CONTRACT.users
    if not isinstance(raw, list):
        raise ConfigError(f"{prefix}: expected list")
    users: list[PlaneUserMapping] = []
    for idx, item in enumerate(raw):
        user_prefix = f"{prefix}[{idx}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{user_prefix}: expected mapping")
        users.append(
            PlaneUserMapping(
                homelab_user=_required_string(item, "homelab_user", user_prefix),
                plane_uuid=_required_string(item, "plane_uuid", user_prefix),
                plane_display_name=_required_string(item, "plane_display_name", user_prefix),
                role=str(item.get("role") or "admin"),
            )
        )
    return tuple(users)


def _required_string(raw: dict[str, Any], field_name: str, prefix: str) -> str:
    value = raw.get(field_name)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"{prefix}.{field_name} is required")
    return str(value)


def _validate_agent(value: str, field_name: str) -> None:
    if value not in {"pi", "claude"}:
        raise ConfigError(f"{field_name} must be one of: pi, claude")


def _reject_yaml_secrets(raw: Any, prefix: str) -> None:
    if isinstance(raw, dict):
        for key, value in raw.items():
            key_text = str(key).lower()
            if key_text in _SECRET_YAML_KEYS or key_text.endswith(("_token", "_secret")):
                raise ConfigError(f"{prefix}.{key}: secrets must come from env, not bindings.yml")
            _reject_yaml_secrets(value, f"{prefix}.{key}")
    elif isinstance(raw, list):
        for idx, value in enumerate(raw):
            _reject_yaml_secrets(value, f"{prefix}[{idx}]")
