from __future__ import annotations

import pytest

from claude_runner import set_claude_probe_failure_reason


@pytest.fixture(autouse=True)
def reset_claude_probe_state():
    set_claude_probe_failure_reason(None)
    yield
    set_claude_probe_failure_reason(None)
