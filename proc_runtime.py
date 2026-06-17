"""Shared process/runtime helpers for Symphony agent runners."""

from __future__ import annotations

import os
import re
from pathlib import Path

RPC_RUNTIME_DIR_ENV = "SYMPHONY_RUNTIME_DIR"
DEFAULT_RUNTIME_DIR = Path("/tmp/symphony")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def pid_start_time(pid: int) -> str:
    """Return the process start-time from ``/proc/<pid>/stat``, or ""."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as handle:
            data = handle.read().decode("utf-8", "replace")
        fields = data[data.rindex(")") + 2 :].split()
        return fields[19]  # starttime: field 22 overall, index 19 after comm
    except (OSError, ValueError, IndexError):
        return ""


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)
