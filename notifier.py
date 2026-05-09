"""Telegram notification for Symphony state transitions."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import escape as _html_escape
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramNotifier:
    bot_token: str
    chat_id: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> TelegramNotifier | None:
        source = os.environ if env is None else env
        token = source.get("TELEGRAM_BOT_TOKEN")
        chat_id = source.get("TELEGRAM_CHAT_ID") or source.get("TELEGRAM_HOME_CHANNEL")
        if not token or not chat_id:
            return None
        return cls(bot_token=token, chat_id=chat_id)

    async def send(self, message: str) -> None:
        import httpx

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10)
                response.raise_for_status()
                LOGGER.info("telegram_notification_sent")
        except Exception as exc:
            LOGGER.warning("telegram_notification_failed error=%s", exc)

    def send_sync(self, message: str) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id,
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
            LOGGER.info("telegram_notification_sent")
            return True
        except Exception as exc:
            LOGGER.warning("telegram_notification_failed error=%s", exc)
            return False


def format_review_message(
    issue_name: str,
    issue_identifier: str = "",
    reason: str = "",
) -> str:
    label = _format_issue_label(issue_name, issue_identifier)
    parts = [f"\U0001f4cb {label} \u2192 <b>Review</b>"]
    if reason:
        parts.append(_html_escape(reason))
    return "\n".join(parts)


def format_blocked_message(
    issue_name: str,
    issue_identifier: str = "",
    reason: str = "",
) -> str:
    label = _format_issue_label(issue_name, issue_identifier)
    parts = [f"\U0001f6ab {label} \u2192 <b>Blocked</b>"]
    if reason:
        parts.append(_html_escape(reason))
    return "\n".join(parts)


def format_scheduled_message(
    issue_name: str,
    issue_identifier: str = "",
    *,
    not_before: str,
    reason: str,
    not_after: str = "",
) -> str:
    label = _format_issue_label(issue_name, issue_identifier)
    parts = [f"\U0001f4c5 {label} \u2192 <b>Scheduled</b>"]
    parts.append(f"not_before: {_html_escape(not_before)}")
    if not_after:
        parts.append(f"advisory_not_after: {_html_escape(not_after)}")
    if reason:
        parts.append(_html_escape(reason))
    return "\n".join(parts)


def format_released_message(
    issue_name: str,
    issue_identifier: str = "",
    *,
    not_before: str,
    reason: str,
    not_after: str = "",
    late: bool = False,
) -> str:
    label = _format_issue_label(issue_name, issue_identifier)
    parts = [f"\U0001f680 {label} \u2192 <b>Released</b>"]
    parts.append(f"not_before: {_html_escape(not_before)}")
    if not_after:
        parts.append(f"advisory_not_after: {_html_escape(not_after)}")
    parts.append(f"late: {'true' if late else 'false'}")
    if reason:
        parts.append(_html_escape(reason))
    return "\n".join(parts)


def _format_issue_label(issue_name: str, issue_identifier: str = "") -> str:
    safe_name = _html_escape(issue_name)
    safe_id = _html_escape(issue_identifier)
    if safe_id and safe_name:
        return f"<b>{safe_id}</b>: {safe_name}"
    if safe_id:
        return f"<b>{safe_id}</b>"
    return safe_name
