from __future__ import annotations

import pytest

from claude_runner import set_claude_probe_failure_reason


@pytest.fixture(autouse=True)
def reset_claude_probe_state():
    set_claude_probe_failure_reason(None)
    yield
    set_claude_probe_failure_reason(None)


@pytest.fixture(autouse=True)
def _no_real_orphan_reap(monkeypatch):
    """Stop any test that exercises ``run_bindings_loop``/``run_dispatcher`` from
    invoking the real orphan reapers.

    The reapers glob the shared host ``/tmp`` (``/tmp/symphony-claude-*.sock``)
    and run real ``tmux kill-server`` / process kills. When the test suite runs
    inside a live Symphony agent (e.g. an agent verifying its own change), an
    unstubbed reaper kills that agent's own tmux socket — the agent dies with a
    bare ``error connecting to ...sock``. This neutralises both reapers by
    default; tests that assert on reaping override this with their own stub.
    """
    import main

    monkeypatch.setattr(
        main, "reap_orphan_claude_sockets", lambda *a, **k: 0, raising=False
    )
    monkeypatch.setattr(
        main, "reap_orphan_rpc_processes", lambda *a, **k: 0, raising=False
    )
    yield


@pytest.fixture(autouse=True)
def _no_background_title_regen(monkeypatch):
    """Neutralise the fire-and-forget post-create title-regeneration thread.

    It invokes the real ``pi`` binary (~20-25s) and schedules on the web app's
    event loop; daemon threads outlive the per-test TestClient loop and leak.
    Tests that exercise regeneration call ``_regenerate_title`` directly.
    """
    from web.api import main as web_main

    monkeypatch.setattr(
        web_main, "_spawn_title_regeneration", lambda *a, **k: None, raising=False
    )
    yield
