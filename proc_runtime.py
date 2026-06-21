"""Shared process/runtime helpers for Symphony agent runners."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

RPC_RUNTIME_DIR_ENV = "SYMPHONY_RUNTIME_DIR"
DEFAULT_RUNTIME_DIR = Path("/tmp/symphony")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def tail_spool_path(run_id: object, environ: Mapping[str, str] | None = None) -> Path:
    """Local file the scheduler spools a run's live agent output to.

    Remote agents write their session transcript on the remote host, so the
    web tailer can't read it directly. But the scheduler already receives the
    pi RPC event stream over the SSH pipe — spooling it here lets the tailer
    stream remote runs from a local file, no second SSH connection (ADR-0019).
    """
    source = os.environ if environ is None else environ
    runtime_dir = Path(source.get(RPC_RUNTIME_DIR_ENV, str(DEFAULT_RUNTIME_DIR)))
    return runtime_dir / "tail" / f"{run_id}.log"


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
