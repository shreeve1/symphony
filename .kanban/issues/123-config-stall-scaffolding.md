---
id: 123
title: Config + data-type scaffolding for stall watchdog
status: pending
blocked_by: []
locks: [config, agent_runner, redispatch_core]
priority: 1
created: 2026-06-25
---

## What to build

Add the three data types the stall watchdog work depends on. No behavior change.

1. **`stall_timeout_ms` config field** — add `stall_timeout_ms: int = 900_000` to `SymphonyConfig` dataclass fields in `config.py`, after `run_timeout_ms`. Wire `from_env()` with `stall_timeout_ms=int(source.get("SYMPHONY_STALL_TIMEOUT_MS", "900000"))`. Insert into `__repr__()` after the `run_timeout_ms` line.

2. **`stalled` flag on `_DrainResult`** — add `stalled: bool = False` field to the `_DrainResult` dataclass in `agent_runner.py`.

3. **`STALL_WATCHDOG_SENTINEL` constant** — define `STALL_WATCHDOG_SENTINEL = "SYMPHONY_STALL_WATCHDOG"` as a module-level constant in `redispatch_core.py`, alongside existing `RETRY_MARKER_PREFIX`.

## Acceptance criteria

- [ ] `SymphonyConfig.__dataclass_fields__` includes `stall_timeout_ms` with default `900_000`
- [ ] `SymphonyConfig.from_env()` reads `SYMPHONY_STALL_TIMEOUT_MS` env var
- [ ] `repr(SymphonyConfig(...))` includes `stall_timeout_ms=900000`
- [ ] `_DrainResult.__dataclass_fields__` includes `stalled` defaulting to `False`
- [ ] `redispatch_core.STALL_WATCHDOG_SENTINEL == "SYMPHONY_STALL_WATCHDOG"`
- [ ] All existing tests pass

## Verification

```bash
uv run python -c "from config import SymphonyConfig; c = SymphonyConfig.__dataclass_fields__; assert 'stall_timeout_ms' in c"
uv run python -c "from config import SymphonyConfig; import os; os.environ['SYMPHONY_STALL_TIMEOUT_MS']='600000'; c = SymphonyConfig.from_env(); assert c.stall_timeout_ms == 600000"
uv run python -c "from config import SymphonyConfig; assert 'stall_timeout_ms=900000' in repr(SymphonyConfig())"
uv run python -c "from agent_runner import _DrainResult; assert 'stalled' in _DrainResult.__dataclass_fields__; d = _DrainResult([], [], False, 0, False, 0); assert d.stalled == False"
uv run python -c "from redispatch_core import STALL_WATCHDOG_SENTINEL; assert STALL_WATCHDOG_SENTINEL == 'SYMPHONY_STALL_WATCHDOG'"
uv run pytest tests/test_config.py tests/test_agent_runner.py -x -q
```

## Blocked by

None — can start immediately
