from __future__ import annotations

import pytest

from plane_adapter import HttpxPlaneTransport, PlaneRateLimitError, _parse_retry_after


@pytest.mark.asyncio
async def test_httpx_transport_raises_rate_limit_with_retry_after(monkeypatch) -> None:
    class FakeResponse:
        status_code = 429
        headers = {"Retry-After": "42"}

        def raise_for_status(self) -> None:
            raise AssertionError("429 should be handled before raise_for_status")

    class FakeClient:
        async def request(self, method, path, json=None):
            return FakeResponse()

        async def aclose(self) -> None:
            pass

    transport = HttpxPlaneTransport("https://plane.test", "key")
    monkeypatch.setattr(transport, "_client", FakeClient())

    with pytest.raises(PlaneRateLimitError) as excinfo:
        await transport.get("/issues/")

    assert excinfo.value.retry_after_s == 42


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", 3),
        ("0", 0),
        (None, None),
        ("not-a-date", None),
    ],
)
def test_parse_retry_after_seconds(value: str | None, expected: float | None) -> None:
    assert _parse_retry_after(value) == expected
