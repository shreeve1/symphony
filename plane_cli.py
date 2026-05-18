#!/usr/bin/env python3
"""Standalone Plane state helper for Symphony-launched agents."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html import escape as _html_escape
from typing import Mapping, Protocol, Sequence

# schedule.py is colocated with plane_cli.py in the symphony repo. Import
# format_*_comment helpers so the CLI shares a single grammar with the
# scheduler and parser. format_*_comment is also our local validator: it
# rejects naive datetimes, inverted not_after<not_before windows, empty/
# whitespace-only/line-breaking reasons.
from schedule import format_cancellation_comment, format_schedule_comment


REQUIRED_ENV = (
    "SYMPHONY_ISSUE_ID",
    "SYMPHONY_PLANE_API_URL",
    "SYMPHONY_PLANE_API_KEY",
    "SYMPHONY_PLANE_PROJECT_ID",
    "SYMPHONY_PLANE_WORKSPACE_SLUG",
)

NOTIFY_STATES = {"review", "blocked"}
COMMENT_MAX_CHARS = 1500
COMMENT_TAIL_CHARS = 500
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_SECRET_ENV_KEYS = (
    "SYMPHONY_PLANE_API_KEY",
    "PLANE_API_KEY",
    "ZAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
)
_REDACTED = "***REDACTED***"

# BEGIN GENERATED PLANE IDS
# Source: homelab_router.plane_contract.DEFAULT_CONTRACT
# Regenerate with: python3 scripts/sync_plane_ids.py
# Drift is enforced by tests/test_plane_cli.py.

STATE_IDS = {
    "done": "ef9d22b5-c69c-4707-8ba3-e3db244f2a84",
    "review": "ea1ccd3d-82d3-4dd4-8226-192941e8e4c0",
    "blocked": "4b226b00-1e1c-46aa-bbd3-b1e04ad6fc1f",
    "todo": "ecdab56c-3d58-4da4-bed0-90f0c665deeb",
}

LABEL_IDS = {
    "patrol": "74f5ab2e-a567-4f8b-8dcf-0908c7ea9ceb",
    "security": "618c2146-78d0-4955-a651-bd0c7ad5712e",
    "infra": "95635e31-ed47-4a2e-96ab-555e43242fa1",
    "network": "cb36e80d-9cea-4935-b9a6-29d3c4d7d90f",
    "media": "a683fbd6-a83a-439f-9e01-123a7088c04d",
    "storage": "cf3e9144-3925-41f0-ac62-3cb7aa3ac480",
    "docker": "c1d39f14-19e0-434a-a183-90bd28ae2875",
    "approval-required": "e7480a55-5ab6-417b-a74a-f436ffcf1db7",
    "plan": "5a022793-c712-4565-ab70-0183fe04c557",
    "build": "4ffc7ef9-9159-455c-b3f9-b3a447157aef",
    "approved": "67839626-ca7f-4c02-a5e0-12e56a35d909",
    "scheduled": "9ac7586e-8745-4c22-8a9d-aa83652bee3e",
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


def _format_agent_comment(text: str, env: Mapping[str, str]) -> str:
    """Sanitize and bound free-form agent comments before posting to Plane."""

    return _sanitize_comment_text(text, env, label="Agent comment")


def _format_display_comment(text: str, env: Mapping[str, str]) -> str:
    """Sanitize and bound Plane comments before printing them to agents."""

    return _sanitize_comment_text(text, env, label="Plane comment")


def _sanitize_comment_text(text: str, env: Mapping[str, str], *, label: str) -> str:
    """Strip terminal noise, redact known secrets, and bound comment text."""

    cleaned = _ANSI_ESCAPE_RE.sub("", text).strip()
    for key in _SECRET_ENV_KEYS:
        secret = env.get(key, "")
        if secret:
            cleaned = cleaned.replace(secret, _REDACTED)
    if len(cleaned) <= COMMENT_MAX_CHARS:
        return cleaned
    first_line = next((line.strip() for line in cleaned.splitlines() if line.strip()), label)
    if len(first_line) > 180:
        first_line = first_line[:179].rstrip() + "…"
    tail = cleaned[-COMMENT_TAIL_CHARS:].strip()
    return (
        f"{first_line}\n\n"
        f"[{label} truncated from {len(cleaned)} characters for Plane readability.]\n\n"
        f"{tail}"
    )


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
    if state == "review":
        emoji = "\U0001f4cb"
        label = "Review"
    elif state == "blocked":
        emoji = "\U0001f6ab"
        label = "Blocked"
    else:
        return
    issue_id = env.get("SYMPHONY_ISSUE_ID", "")
    parts = [f"{emoji} Issue {issue_id} \u2192 <b>{label}</b>"]
    issue_url = _build_issue_url(env, issue_id)
    if issue_url:
        parts.append(f'\U0001f517 <a href="{_html_escape(issue_url)}">Open issue</a>')
    dashboard_url = env.get("PLANE_DASHBOARD_URL", "")
    if dashboard_url:
        parts.append(f'\U0001f4ca <a href="{_html_escape(dashboard_url)}">Dashboard</a>')
    _send_telegram_message(env, "\n".join(parts))


def _build_issue_url(env: Mapping[str, str], issue_id: str) -> str:
    """Derive the Plane frontend issue URL from agent env vars.

    Returns an empty string if any required component is missing so callers
    can safely skip the URL without crashing.
    """
    if not issue_id:
        return ""
    base_url = (env.get("SYMPHONY_PLANE_FRONTEND_URL") or env.get("SYMPHONY_PLANE_API_URL", "")).rstrip("/")
    workspace = env.get("SYMPHONY_PLANE_WORKSPACE_SLUG", "")
    project_id = env.get("SYMPHONY_PLANE_PROJECT_ID", "")
    if not base_url or not workspace or not project_id:
        return ""
    from urllib.parse import urlparse
    if env.get("SYMPHONY_PLANE_FRONTEND_URL"):
        base = base_url
    else:
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/{workspace}/projects/{project_id}/issues/{issue_id}/"


def _send_telegram_message(env: Mapping[str, str], message: str) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return
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
        raise PlaneCliError(
            "Usage: plane <done|review|blocked|comment|comments|label|unlabel"
            "|schedule|unschedule ...>"
        )
    if args[0] == "plane":
        args = args[1:]
    if not args:
        raise PlaneCliError(
            "Usage: plane <done|review|blocked|comment|comments|label|unlabel"
            "|schedule|unschedule ...>"
        )

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
        client.post(config.comment_path(), {"comment_html": _format_agent_comment(" ".join(args[1:]), env)})
        return 0

    if command == "label":
        if len(args) != 2:
            raise PlaneCliError("Usage: plane label <label-name>")
        label_name = args[1]
        if label_name not in LABEL_IDS:
            raise PlaneCliError(
                f"Unknown label: {label_name}. Available: {', '.join(sorted(LABEL_IDS))}"
            )
        _add_label(client, config, label_name)
        return 0

    if command == "unlabel":
        if len(args) != 2:
            raise PlaneCliError("Usage: plane unlabel <label-name>")
        label_name = args[1]
        if label_name not in LABEL_IDS:
            raise PlaneCliError(
                f"Unknown label: {label_name}. Available: {', '.join(sorted(LABEL_IDS))}"
            )
        _remove_label(client, config, label_name)
        return 0

    if command == "comments":
        response = client.get(config.comment_path())
        comments = response.get("results", [])
        comments.sort(key=lambda c: c.get("created_at", ""))
        for i, comment in enumerate(comments):
            if i > 0:
                print("---")
            print(_format_display_comment(str(comment.get("comment_html", "")), env))
        return 0

    if command == "schedule":
        not_before, reason, not_after = _parse_schedule_args(args[1:])
        # Fail fast on missing generated IDs before any API calls so the
        # operator sees the drift immediately rather than after a partial
        # mutation. Plan tasks 4.7 + 2.5/2.6 require todo + scheduled to
        # exist in the regenerated CLI.
        if "scheduled" not in LABEL_IDS:
            raise PlaneCliError(
                "plane_cli is missing the 'scheduled' label id; "
                "run scripts/sync_plane_ids.py to regenerate"
            )
        if "todo" not in STATE_IDS:
            raise PlaneCliError(
                "plane_cli is missing the 'todo' state id; "
                "run scripts/sync_plane_ids.py to regenerate"
            )
        # format_schedule_comment is our local validator: it rejects naive
        # datetimes, inverted windows, and empty/whitespace-only/line-
        # breaking reasons. Validate BEFORE any mutation so partial failure
        # can't leave the ticket scheduled-without-comment or vice versa.
        body = format_schedule_comment(
            not_before=not_before, reason=reason, not_after=not_after
        )
        # Order matters: comment first (audit trail), then label add, then
        # state transition. The scheduler's release path mirrors this:
        # audit comment first, then label removal. If the comment POST
        # fails, no label is added, no state changes, and the operator
        # sees the error.
        client.post(config.comment_path(), {"comment_html": body})
        _add_label(client, config, "scheduled")
        client.patch(config.issue_path(), {"state": STATE_IDS["todo"]})
        return 0

    if command == "unschedule":
        reason = _parse_unschedule_args(args[1:])
        if "scheduled" not in LABEL_IDS:
            raise PlaneCliError(
                "plane_cli is missing the 'scheduled' label id; "
                "run scripts/sync_plane_ids.py to regenerate"
            )
        if "todo" not in STATE_IDS:
            raise PlaneCliError(
                "plane_cli is missing the 'todo' state id; "
                "run scripts/sync_plane_ids.py to regenerate"
            )
        body = format_cancellation_comment(reason=reason)
        # Plan task 4.5: comment + remove scheduled label; do NOT force a
        # state transition. The ticket may have already been moved out of
        # Todo (e.g. directly to Cancelled by a human operator) and the
        # CLI must not undo that.
        client.post(config.comment_path(), {"comment_html": body})
        _remove_label(client, config, "scheduled")
        return 0

    raise PlaneCliError(f"Unknown command: {command}")


def _parse_schedule_args(rest: Sequence[str]) -> tuple[datetime, str, datetime | None]:
    """Parse `--not-before <iso> --reason <text> [--not-after <iso>]`.

    Returns (not_before, reason, not_after_or_None) parsed via
    datetime.fromisoformat. format_schedule_comment performs the strict
    semantic validation (offset/Z required, no inverted window, reason
    non-empty and non-line-breaking).
    """
    options = _parse_named_args(
        rest,
        required={"--not-before", "--reason"},
        allowed={"--not-before", "--not-after", "--reason"},
        usage="Usage: plane schedule --not-before <iso> --reason <text> [--not-after <iso>]",
    )
    not_before = _parse_iso_arg(options["--not-before"], "--not-before")
    not_after_raw = options.get("--not-after")
    not_after = _parse_iso_arg(not_after_raw, "--not-after") if not_after_raw else None
    return not_before, options["--reason"], not_after


def _parse_unschedule_args(rest: Sequence[str]) -> str:
    """Parse `--reason <text>` for `plane unschedule`."""
    options = _parse_named_args(
        rest,
        required={"--reason"},
        allowed={"--reason"},
        usage="Usage: plane unschedule --reason <text>",
    )
    return options["--reason"]


def _parse_named_args(
    rest: Sequence[str],
    *,
    required: set[str],
    allowed: set[str],
    usage: str,
) -> dict[str, str]:
    """Tokenise `--key value` pairs and `--key=value` forms.

    Rejects unknown flags, missing values, duplicates, and bare positional
    arguments so the CLI grammar stays explicit. Target-override flags
    (--issue, --target, ...) are already filtered out by the global
    _reject_target_override; this helper enforces the per-command
    allow-list.
    """
    options: dict[str, str] = {}
    i = 0
    while i < len(rest):
        token = rest[i]
        if not token.startswith("--"):
            raise PlaneCliError(f"Unexpected positional argument: {token!r}. {usage}")
        if "=" in token:
            key, value = token.split("=", 1)
        else:
            key = token
            if i + 1 >= len(rest):
                raise PlaneCliError(f"Missing value for {key}. {usage}")
            value = rest[i + 1]
            i += 1
        if key not in allowed:
            raise PlaneCliError(f"Unknown option {key!r}. {usage}")
        if key in options:
            raise PlaneCliError(f"Duplicate option {key!r}. {usage}")
        options[key] = value
        i += 1
    missing = required - options.keys()
    if missing:
        raise PlaneCliError(
            f"Missing required option(s): {', '.join(sorted(missing))}. {usage}"
        )
    return options


def _parse_iso_arg(value: str, flag: str) -> datetime:
    """Parse ISO 8601 with explicit offset; defer strict validation to schedule.format_*."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PlaneCliError(f"{flag} is not a valid ISO 8601 datetime: {value!r}") from exc
    if parsed.tzinfo is None:
        raise PlaneCliError(f"{flag} must include an explicit UTC offset: {value!r}")
    return parsed


def _add_label(client: Transport, config: PlaneCliConfig, label_name: str) -> None:
    """GET-merge-PATCH preserving unrelated labels (plan task 4.6)."""
    current = client.get(config.issue_path())
    existing_uuids: list[str] = list(current.get("labels") or [])
    new_uuid = LABEL_IDS[label_name]
    merged = list(dict.fromkeys(existing_uuids + [new_uuid]))
    client.patch(config.issue_path(), {"labels": merged})


def _remove_label(client: Transport, config: PlaneCliConfig, label_name: str) -> None:
    """GET-subtract-PATCH preserving unrelated labels (plan task 4.6)."""
    current = client.get(config.issue_path())
    existing_uuids: list[str] = list(current.get("labels") or [])
    remove_uuid = LABEL_IDS[label_name]
    remaining = [u for u in existing_uuids if u != remove_uuid]
    client.patch(config.issue_path(), {"labels": remaining})


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except PlaneCliError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
