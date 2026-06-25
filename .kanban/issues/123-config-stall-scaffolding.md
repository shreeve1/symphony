---
id: 123
title: Config + data-type scaffolding for stall watchdog
status: done
blocked_by: []
locks: [config, agent_runner, redispatch_core]
priority: 1
created: 2026-06-25
updated: 2026-06-25
actor: ralph
action_reviewed: 2026-06-25
---

## What to build

Add the three data types the stall watchdog work depends on. No behavior change.

1. **`stall_timeout_ms` config field** — add `stall_timeout_ms: int = 900_000` to `SymphonyConfig` dataclass fields in `config.py`, after `run_timeout_ms`. Wire `from_env()` with `stall_timeout_ms=int(source.get("SYMPHONY_STALL_TIMEOUT_MS", "900000"))`. Insert into `__repr__()` after the `run_timeout_ms` line.

2. **`stalled` flag on `_DrainResult`** — add `stalled: bool = False` field to the `_DrainResult` dataclass in `agent_runner.py`.

3. **`STALL_WATCHDOG_SENTINEL` constant** — define `STALL_WATCHDOG_SENTINEL = "SYMPHONY_STALL_WATCHDOG"` as a module-level constant in `redispatch_core.py`, alongside existing `RETRY_MARKER_PREFIX`.

## Acceptance criteria

- [x] `SymphonyConfig.__dataclass_fields__` includes `stall_timeout_ms` with default `900_000`
- [x] `SymphonyConfig.from_env()` reads `SYMPHONY_STALL_TIMEOUT_MS` env var
- [x] `repr(SymphonyConfig(...))` includes `stall_timeout_ms=900000`
- [x] `_DrainResult.__dataclass_fields__` includes `stalled` defaulting to `False`
- [x] `redispatch_core.STALL_WATCHDOG_SENTINEL == "SYMPHONY_STALL_WATCHDOG"`
- [x] All existing tests pass

## Verification

```bash
uv run python -c "from config import SymphonyConfig; c = SymphonyConfig.__dataclass_fields__; assert 'stall_timeout_ms' in c"
uv run python -c "from config import SymphonyConfig; env={'SYMPHONY_BINDINGS_PATH':'/nonexistent','PLANE_API_URL':'http://x','PLANE_API_KEY':'k','PLANE_WORKSPACE_SLUG':'w','PLANE_PROJECT_ID':'p','HOMELAB_REPO_PATH':'/tmp','PI_BIN':'/bin/true','SYMPHONY_STALL_TIMEOUT_MS':'600000'}; c = SymphonyConfig.from_env(env); assert c.stall_timeout_ms == 600000"
uv run python -c "from config import SymphonyConfig; from pathlib import Path; assert 'stall_timeout_ms=900000' in repr(SymphonyConfig(plane_api_url='x', plane_api_key='k', plane_workspace_slug='w', plane_project_id='p', homelab_repo_path=Path('/tmp'), pi_bin='/bin/true'))"
uv run python -c "from agent_runner import _DrainResult; assert 'stalled' in _DrainResult.__dataclass_fields__; d = _DrainResult([], [], False, 0, False, 0); assert d.stalled == False"
uv run python -c "from redispatch_core import STALL_WATCHDOG_SENTINEL; assert STALL_WATCHDOG_SENTINEL == 'SYMPHONY_STALL_WATCHDOG'"
uv run pytest tests/test_config.py tests/test_agent_runner.py -x -q
```

## Implementation Notes

Added the stall timeout config field/env/repr support, the `_DrainResult.stalled` flag, and the shared `STALL_WATCHDOG_SENTINEL`. Fixed the verification block to avoid ambient service env and zero-arg `SymphonyConfig()` assumptions while still exercising the same criteria.

## Blocked by

None — can start immediately
