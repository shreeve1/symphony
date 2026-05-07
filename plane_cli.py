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

NOTIFY_STATES = {"review", "blocked"}

# BEGIN GENERATED PLANE IDS
# Source: homelab_router.plane_contract.DEFAULT_CONTRACT
# Regenerate with: python3 scripts/sync_plane_ids.py
# Drift is enforced by tests/test_plane_cli.py.

STATE_IDS = {
    "done": "ef9d22b5-c69c-4707-8ba3-e3db244f2a84",
    "review": "ea1ccd3d-82d3-4dd4-8226-192941e8e4c0",
    "blocked": "4b226b00-1e1c-46aa-bbd3-b1e04ad6fc1f",
}

LABEL_IDS = {
    "media": "a683fbd6-a83a-439f-9e01-123a7088c04d",
    "approval-required": "e7480a55-5ab6-417b-a74a-f436ffcf1db7",
    "plan": "5a022793-c712-4565-ab70-0183fe04c557",
    "build": "4ffc7ef9-9159-455c-b3f9-b3a447157aef",
    "approved": "67839626-ca7f-4c02-a5e0-12e56a35d909",
}
# END GENERATED PLANE IDS


class PlaneCliError(RuntimeError):
    """Raised for expected CLI failures."""


class Transport(Protocol):
    def get(self, path: str) -> dict: ...
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
            f"/projects/{self.project_id}/issues/{self.issue_id}/"
        )

    def comment_path(self) -> str:
        return f"{self.issue_path()}comments/"


class UrllibTransport:
    def __init__(self, config: PlaneCliConfig) -> None:
        self._config = config

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def patch(self, path: str, body: dict[str, str]) -> None:
        self._request("PATCH", path, body)

    def post(self, path: str, body: dict[str, str]) -> None:
        self._request("POST", path, body)

    def _request(
        self, method: str, path: str, body: dict[str, str] | None = None
    ) -> dict:
        data = json.dumps(body).encode("utf-8") if body else None
        request = urllib.request.Request(
            f"{self._config.api_url}{path}",
            data=data,
            method=method,
            headers={
                "X-API-Key": self._config.api_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
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


def _send_telegram(env: Mapping[str, str], state: str) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return
    if state == "review":
        emoji = "\U0001f4cb"
        label = "Review"
    elif state == "blocked":
        emoji = "\U0001f6ab"
        label = "Blocked"
    else:
        return
    issue_id = env.get("SYMPHONY_ISSUE_ID", "")
    message = f"{emoji} Issue {issue_id} \u2192 <b>{label}</b>"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception:
        pass


def run(
    argv: Sequence[str],
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> int:
    env = os.environ if env is None else env
    args = list(argv)
    _reject_target_override(args)

    if not args:
        raise PlaneCliError("Usage: plane <done|review|blocked|comment|comments|label|unlabel ...>")
    if args[0] == "plane":
        args = args[1:]
    if not args:
        raise PlaneCliError("Usage: plane <done|review|blocked|comment|comments|label|unlabel ...>")

    config = PlaneCliConfig.from_env(env)
    client = transport or UrllibTransport(config)
    command = args[0]

    if command in STATE_IDS:
        if len(args) != 1:
            raise PlaneCliError(f"plane {command} does not accept an issue argument")
        client.patch(config.issue_path(), {"state": STATE_IDS[command]})
        if command in NOTIFY_STATES:
            _send_telegram(env, command)
        return 0

    if command == "comment":
        if len(args) < 2:
            raise PlaneCliError("plane comment requires comment text")
        client.post(config.comment_path(), {"comment_html": " ".join(args[1:])})
        return 0

    if command == "label":
        if len(args) != 2:
            raise PlaneCliError("Usage: plane label <label-name>")
        label_name = args[1]
        if label_name not in LABEL_IDS:
            raise PlaneCliError(
                f"Unknown label: {label_name}. Available: {', '.join(sorted(LABEL_IDS))}"
            )
        current = client.get(config.issue_path())
        existing_uuids: list[str] = list(current.get("labels") or [])
        new_uuid = LABEL_IDS[label_name]
        merged = list(dict.fromkeys(existing_uuids + [new_uuid]))
        client.patch(config.issue_path(), {"labels": merged})
        return 0

    if command == "unlabel":
        if len(args) != 2:
            raise PlaneCliError("Usage: plane unlabel <label-name>")
        label_name = args[1]
        if label_name not in LABEL_IDS:
            raise PlaneCliError(
                f"Unknown label: {label_name}. Available: {', '.join(sorted(LABEL_IDS))}"
            )
        current = client.get(config.issue_path())
        existing_uuids: list[str] = list(current.get("labels") or [])
        remove_uuid = LABEL_IDS[label_name]
        remaining = [u for u in existing_uuids if u != remove_uuid]
        client.patch(config.issue_path(), {"labels": remaining})
        return 0

    if command == "comments":
        response = client.get(config.comment_path())
        comments = response.get("results", [])
        comments.sort(key=lambda c: c.get("created_at", ""))
        for i, comment in enumerate(comments):
            if i > 0:
                print("---")
            print(comment.get("comment_html", ""))
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
