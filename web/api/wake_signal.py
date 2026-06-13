"""Cross-process wake signal for fast scheduler re-dispatch."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

WAKE_SENTINEL_PATH_ENV = "SYMPHONY_WAKE_SENTINEL_PATH"
RUNTIME_DIR_ENV = "SYMPHONY_RUNTIME_DIR"
DEFAULT_RUNTIME_DIR = Path("/tmp/symphony")
WAKE_SENTINEL_NAME = "reply-wake"


def wake_sentinel_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the shared wake sentinel path for API and scheduler processes."""

    source = os.environ if env is None else env
    configured_path = source.get(WAKE_SENTINEL_PATH_ENV)
    if configured_path:
        return Path(configured_path)
    runtime_dir = Path(source.get(RUNTIME_DIR_ENV, str(DEFAULT_RUNTIME_DIR)))
    return runtime_dir / WAKE_SENTINEL_NAME


def touch_wake_sentinel(path: Path | None = None) -> Path:
    """Create or update the wake sentinel and return its path."""

    sentinel = path or wake_sentinel_path()
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.touch(exist_ok=True)
    return sentinel


def consume_wake_sentinel(path: Path | None = None) -> bool:
    """Remove a pending wake sentinel. Return True when one was consumed."""

    sentinel = path or wake_sentinel_path()
    try:
        sentinel.unlink()
    except FileNotFoundError:
        return False
    return True
