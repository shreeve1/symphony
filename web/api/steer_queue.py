"""Transient file queue for live pi RPC steering records."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

STEER_RUNTIME_DIR_ENV = "SYMPHONY_RUNTIME_DIR"
_DEFAULT_RUNTIME_DIR = Path("/tmp/symphony")
SteerKind = Literal["steer", "abort"]


@dataclass(frozen=True)
class SteerRecord:
    id: str
    run_id: str
    issue_id: str
    kind: SteerKind
    message: str
    created_at: str


def steer_queue_dir(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    return Path(source.get(STEER_RUNTIME_DIR_ENV, str(_DEFAULT_RUNTIME_DIR))) / "steer"


def steer_queue_path(run_id: str, environ: Mapping[str, str] | None = None) -> Path:
    return steer_queue_dir(environ) / f"{run_id}.jsonl"


def write_steer_record(
    run_id: str,
    issue_id: str,
    *,
    kind: SteerKind,
    message: str = "",
    created_at: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> SteerRecord:
    if kind == "steer" and not message.strip():
        raise ValueError("steer message cannot be empty")
    record = SteerRecord(
        id=str(uuid4()),
        run_id=str(run_id),
        issue_id=str(issue_id),
        kind=kind,
        message=message.strip(),
        created_at=created_at or datetime.now(UTC).isoformat(),
    )
    path = steer_queue_path(str(run_id), environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return record


def read_steer_records(
    run_id: str,
    offset: int = 0,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Read complete queued records after offset and return the new offset.

    Missing, truncated, or malformed queue files degrade safely. A partial final
    line is left unread until it receives a newline, so a concurrent append
    cannot produce a half-delivered steer.
    """
    path = steer_queue_path(str(run_id), environ)
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset
    if offset > size:
        offset = 0
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except OSError:
        return [], offset
    if not data:
        return [], offset
    last_newline = data.rfind(b"\n")
    if last_newline == -1:
        return [], offset
    consumed = data[: last_newline + 1]
    new_offset = offset + len(consumed)
    records: list[dict[str, Any]] = []
    for raw_line in consumed.splitlines():
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind not in ("steer", "abort"):
            continue
        records.append(record)
    return records, new_offset


def clear_steer_queue(
    run_id: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Remove one transient queue file. Returns True when a file was removed."""

    path = steer_queue_path(str(run_id), environ)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def clear_stale_steer_queues(*, environ: Mapping[str, str] | None = None) -> int:
    """Remove all transient queue files at scheduler startup."""

    directory = steer_queue_dir(environ)
    try:
        paths = sorted(directory.glob("*.jsonl"))
    except OSError:
        return 0
    count = 0
    for path in paths:
        try:
            path.unlink()
        except OSError:
            continue
        count += 1
    return count
