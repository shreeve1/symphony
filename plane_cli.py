"""Standalone Plane state helper for Symphony-launched agents."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


REQUIRED_ENV = (
    "SYMPHONY_ISSUE_ID",
    "SYMPHONY_PLANE_API_URL",
    "SYMPHONY_PLANE_API_KEY",
    "SYMPHONY_PLANE_PROJECT_ID",
    "SYMPHONY_PLANE_WORKSPACE_SLUG",
)

STATE_IDS = {
    "done": "ef9d22b5-c69c-4707-8ba3-e3db244f2a84",
    "review": "ea1ccd3d-82d3-4dd4-8226-192941e8e4c0",
    "blocked": "4b226b00-1e1c-46aa-bbd3-b1e04ad6fc1f",
}


class PlaneCliError(RuntimeError):
    """Raised for expected CLI failures."""


class Transport(Protocol):
    def patch(self, path: str, body: dict[str, str]) -> None: ...
    def post(self, path: str, body: dict[str, str]) -> None: ...


@dataclass(frozen=True)
class PlaneCliConfig:
    issue_id: str
    api_url: str
    api_key: str
    project_id: str
    workspace_slug: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "PlaneCliConfig":
        missing = [name for name in REQUIRED_ENV if not env.get(name)]
        if missing:
            raise PlaneCliError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        return cls(
            issue_id=env["SYMPHONY_ISSUE_ID"],
            api_url=env["SYMPHONY_PLANE_API_URL"].rstrip("/"),
            api_key=env["SYMPHONY_PLANE_API_KEY"],
            project_id=env["SYMPHONY_PLANE_PROJECT_ID"],
            workspace_slug=env["SYMPHONY_PLANE_WORKSPACE_SLUG"],
        )

    def issue_path(self) -> str:
        return (
            f"/api/v1/workspaces/{self.workspace_slug}"
            f"/projects/{self.project_id}/issues/{self.issue_id}"
        )

    def comment_path(self) -> str:
        return f"{self.issue_path()}/comments"


class UrllibTransport:
    def __init__(self, config: PlaneCliConfig) -> None:
        self._config = config

    def patch(self, path: str, body: dict[str, str]) -> None:
        self._request("PATCH", path, body)

    def post(self, path: str, body: dict[str, str]) -> None:
        self._request("POST", path, body)

    def _request(self, method: str, path: str, body: dict[str, str]) -> None:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self._config.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status >= 400:
                    raise PlaneCliError(f"Plane API error: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            raise PlaneCliError(f"Plane API error: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise PlaneCliError(f"Plane API error: {exc.reason}") from exc


def _reject_target_override(args: Sequence[str]) -> None:
    forbidden = {"--issue", "--issue-id", "--target", "--target-issue"}
    if any(
        arg in forbidden or any(arg.startswith(f"{flag}=") for flag in forbidden)
        for arg in args
    ):
        raise PlaneCliError(
            "Issue target override is not allowed; using SYMPHONY_ISSUE_ID"
        )


def run(
    argv: Sequence[str],
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> int:
    env = os.environ if env is None else env
    args = list(argv)
    _reject_target_override(args)

    if not args:
        raise PlaneCliError("Usage: plane <done|review|blocked|comment <text>>")
    if args[0] == "plane":
        args = args[1:]
    if not args:
        raise PlaneCliError("Usage: plane <done|review|blocked|comment <text>>")

    config = PlaneCliConfig.from_env(env)
    client = transport or UrllibTransport(config)
    command = args[0]

    if command in STATE_IDS:
        if len(args) != 1:
            raise PlaneCliError(f"plane {command} does not accept an issue argument")
        client.patch(config.issue_path(), {"state": STATE_IDS[command]})
        return 0

    if command == "comment":
        if len(args) < 2:
            raise PlaneCliError("plane comment requires comment text")
        client.post(config.comment_path(), {"comment_html": " ".join(args[1:])})
        return 0

    raise PlaneCliError(f"Unknown command: {command}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except PlaneCliError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
