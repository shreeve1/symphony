"""Environment configuration for the Symphony service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


_REQUIRED_ENV = (
    "PLANE_API_URL",
    "PLANE_API_KEY",
    "PLANE_WORKSPACE_SLUG",
    "PLANE_PROJECT_ID",
    "HOMELAB_REPO_PATH",
    "PI_BIN",
)


@dataclass(frozen=True)
class SymphonyConfig:
    """Runtime config loaded from environment variables."""

    plane_api_url: str
    plane_api_key: str = field(repr=False)
    plane_workspace_slug: str
    plane_project_id: str
    homelab_repo_path: Path
    pi_bin: str
    pi_provider: str = "zai"
    pi_model: str = "glm-5.1:high"
    poll_interval_ms: int = 30_000
    run_timeout_ms: int = 1_800_000
    lock_path: Path = Path("/tmp/symphony.lock")
    telegram_bot_token: str | None = field(default=None, repr=False)
    telegram_chat_id: str | None = None
    plane_frontend_url: str = ""
    plane_dashboard_url: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "SymphonyConfig":
        source = os.environ if env is None else env
        missing = [name for name in _REQUIRED_ENV if not source.get(name)]
        if missing:
            raise EnvironmentError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        return cls(
            plane_api_url=source["PLANE_API_URL"].rstrip("/"),
            plane_api_key=source["PLANE_API_KEY"],
            plane_workspace_slug=source["PLANE_WORKSPACE_SLUG"],
            plane_project_id=source["PLANE_PROJECT_ID"],
            homelab_repo_path=Path(source["HOMELAB_REPO_PATH"]),
            pi_bin=source["PI_BIN"],
            pi_provider=source.get("SYMPHONY_PI_PROVIDER", "zai"),
            pi_model=source.get("SYMPHONY_PI_MODEL", "glm-5.1:high"),
            poll_interval_ms=int(source.get("SYMPHONY_POLL_INTERVAL_MS", "30000")),
            run_timeout_ms=int(source.get("SYMPHONY_RUN_TIMEOUT_MS", "1800000")),
            lock_path=Path(source.get("SYMPHONY_LOCK_PATH", str(Path(source["HOMELAB_REPO_PATH"]) / ".symphony.lock"))),
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=source.get("TELEGRAM_CHAT_ID") or source.get("TELEGRAM_HOME_CHANNEL"),
            plane_frontend_url=source.get("PLANE_FRONTEND_URL", "").rstrip("/"),
            plane_dashboard_url=source.get("PLANE_DASHBOARD_URL", ""),
        )

    def issue_url(self, issue_id: str) -> str:
        """Return the Plane frontend URL for a specific issue.

        Derived from the base URL (scheme+host[:port] only) plus the standard
        Plane frontend path pattern.  Returns an empty string if issue_id is
        empty so callers can safely pass the result to format_*_message.
        """
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
            f"lock_path={self.lock_path!r}, "
            f"telegram_chat_id={telegram_chat_id!r}, "
            f"plane_frontend_url={self.plane_frontend_url!r}, "
            f"plane_dashboard_url={self.plane_dashboard_url!r})"
        )

    __str__ = __repr__
