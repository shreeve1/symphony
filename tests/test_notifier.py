from __future__ import annotations

import json
from typing import Any

import pytest

from notifier import (
    TelegramNotifier,
    format_blocked_message,
    format_review_message,
)


class FakeHttpxResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class FakeHttpxClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url: str, json: dict[str, Any], timeout: int = 10) -> FakeHttpxResponse:
        self.calls.append((url, json))
        if self.fail:
            return FakeHttpxResponse(status_code=500)
        return FakeHttpxResponse()


def _notifier() -> TelegramNotifier:
    return TelegramNotifier(bot_token="123456:ABC", chat_id="999")


def test_from_env_returns_notifier_when_both_set():
    env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"}
    n = TelegramNotifier.from_env(env)
    assert n is not None
    assert n.bot_token == "tok"
    assert n.chat_id == "chat"


def test_from_env_falls_back_to_home_channel():
    env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_HOME_CHANNEL": "home"}
    n = TelegramNotifier.from_env(env)
    assert n is not None
    assert n.chat_id == "home"


def test_from_env_prefers_chat_id_over_home_channel():
    env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat", "TELEGRAM_HOME_CHANNEL": "home"}
    n = TelegramNotifier.from_env(env)
    assert n.chat_id == "chat"


def test_from_env_returns_none_when_token_missing():
    assert TelegramNotifier.from_env({"TELEGRAM_CHAT_ID": "chat"}) is None


def test_from_env_returns_none_when_chat_id_missing():
    assert TelegramNotifier.from_env({"TELEGRAM_BOT_TOKEN": "tok"}) is None


def test_from_env_returns_none_when_empty():
    assert TelegramNotifier.from_env({}) is None


@pytest.mark.asyncio
async def test_send_posts_to_telegram_api():
    notifier = _notifier()
    client = FakeHttpxClient()

    import httpx

    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda: client  # type: ignore[assignment]
    try:
        await notifier.send("hello")
    finally:
        httpx.AsyncClient = original_client  # type: ignore[assignment]

    assert len(client.calls) == 1
    url, payload = client.calls[0]
    assert "bot123456:ABC/sendMessage" in url
    assert payload["chat_id"] == "999"
    assert payload["text"] == "hello"
    assert payload["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_send_logs_warning_on_failure(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="notifier"):
        notifier = _notifier()
        client = FakeHttpxClient(fail=True)

        import httpx

        original_client = httpx.AsyncClient
        httpx.AsyncClient = lambda: client  # type: ignore[assignment]
        try:
            await notifier.send("hello")
        finally:
            httpx.AsyncClient = original_client  # type: ignore[assignment]

    assert any("telegram_notification_failed" in r.message for r in caplog.records)


def test_send_sync_posts_to_telegram_api(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeResponse:
        def read(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["data"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = _notifier()
    result = notifier.send_sync("sync hello")

    assert result is True
    assert "bot123456:ABC/sendMessage" in captured["url"]
    assert captured["data"]["text"] == "sync hello"
    assert captured["data"]["parse_mode"] == "HTML"


def test_send_sync_returns_false_on_failure(monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = _notifier()
    result = notifier.send_sync("fail")

    assert result is False


def test_format_review_message_basic():
    msg = format_review_message("Fix storage issue")
    assert "Review" in msg
    assert "Fix storage issue" in msg


def test_format_review_message_with_identifier():
    msg = format_review_message("Fix storage issue", "INFRA-042")
    assert "<b>INFRA-042</b>" in msg
    assert "Fix storage issue" in msg


def test_format_review_message_with_reason():
    msg = format_review_message("Fix storage issue", reason="Plan mode completed")
    assert "Plan mode completed" in msg


def test_format_blocked_message_basic():
    msg = format_blocked_message("Deploy failed")
    assert "Blocked" in msg
    assert "Deploy failed" in msg


def test_format_blocked_message_with_identifier_and_reason():
    msg = format_blocked_message("Deploy failed", "OPS-7", "Agent crashed")
    assert "<b>OPS-7</b>" in msg
    assert "Agent crashed" in msg


def test_format_review_message_escapes_html():
    msg = format_review_message("Fix <bug> & stuff", "INFRA-1", 'Reason: "oops" <script>')
    assert "&lt;bug&gt;" in msg
    assert "&amp;" in msg
    assert "&lt;script&gt;" in msg
    assert "<bug>" not in msg


def test_format_blocked_message_escapes_html():
    msg = format_blocked_message("Deploy <fail>", "OPS-7", "Error & crash")
    assert "&lt;fail&gt;" in msg
    assert "&amp;" in msg
    assert "<fail>" not in msg
