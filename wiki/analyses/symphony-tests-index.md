---
title: Symphony tests index
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - tests/*.py
confidence: high
tags: [tests, pytest, coverage-map, fake-transport]
---

# Symphony tests index

`tests/` holds 14 `test_*.py` files; 435 tests total (counted from `def test_` + `async def test_`). The test directory is the contract documentation for behaviours not in `CONTEXT.md` or the ADRs.

## File → module → test count

| Test file | Module under test | Tests | Notes |
|---|---|---|---|
| `test_scheduler.py` | `scheduler.py` (2633 LOC) | **160** | by far the largest suite; covers dispatch, claim, finalize, sanitisation, schedule release, reconcile paths, rate-limit cooldown, dirty-base approval, Telegram fire-and-forget |
| `test_schedule.py` | `schedule.py` | 57 | exhaustive parser cases: HTML normalisation, quote escapes, sort precedence, hard invariants — see [schedule-comment-grammar](../concepts/schedule-comment-grammar.md) |
| `test_plane_cli.py` | `plane_cli.py` | 53 | the `plane done|review|blocked|schedule|unschedule|label|unlabel|comments` shim entry points |
| `test_project_scaffold.py` | `project_scaffold.py` | 32 | `symphony-project-scaffold` skill backing |
| `test_notifier.py` | `notifier.py` | 27 | Telegram notifier: config resolution, async/sync sending, failure handling, review/blocked message format, URL links, schedule/release message format |
| `test_config.py` | `config.py` | 25 | `from_env`, `ProjectBinding`, lock-path resolution, agent override, landing/approval policies |
| `test_plane_poller.py` | `plane_poller.py` | 23 | pagination caps, mixed-state pagination, candidate extraction |
| `test_blocked_reconciler.py` | `blocked_reconciler.py` | 18 | rule evaluation, page caps, distinct-pass counting, approval-required skip — see [blocked-reconciler-implementation](../concepts/blocked-reconciler-implementation.md) |
| `test_agent_runner.py` | `agent_runner.py` | 16 | `verify_pi_support` probe success/failure, silent-exit guardrail (C-0025), tmux send-keys path, RoutingAgentAdapter selection |
| `test_run_worktree.py` | `run_worktree.py` | 7 | naming scheme, create/remove lifecycle, tmux socket helpers |
| `test_main.py` | `main.py` | 7 | startup sequence — env loading, verify_pi_support call ordering |
| `test_code_version.py` | `code_version.py` | 4 | `_CODE_SHA` resolution at import |
| `test_prompt_renderer.py` | `prompt_renderer.py` | 4 | front-matter parse, variable substitution, conversation context block, schedule context |
| `test_plane_adapter.py` | `plane_adapter.py` (641 LOC) | 2 | thin: adapter behaviour is mostly exercised through scheduler tests with `FakeTransport` |

## Per-test-file size signals

- **`test_scheduler.py` 160 tests** is a coverage hotspot. Any scheduler change is expected to add or modify tests here. The brainstorm's spec-review brief reports "uv run pytest -q: 249 passed" from a prior moment; today's count is 435.
- **`test_schedule.py` 57 tests** is comparable in density to the module's 787 LOC. Reflects the round-4 audit findings called out in `schedule.py` docstrings.
- **`test_plane_adapter.py` only 2 tests** is intentional — adapter behaviour is exercised end-to-end through `test_scheduler.py` using `FakeTransport` (mentioned in the plan-approve workflow plan: `FakeTransport needs labels tracking and GET support for tests`).

## Validation contract (from spec PRDs)

The pi-swap audit briefs codified the validation Symphony expects against the current tree:

```bash
cd /home/james/symphony
python3 -m pytest -q                  # expected: PASS
python3 -m py_compile *.py            # expected: exit 0
git diff --check                      # expected: clean whitespace
```

And for safe scheduling-area changes:

```bash
python3 -m pytest tests/test_schedule.py tests/test_plane_cli.py tests/test_plane_poller.py tests/test_scheduler.py tests/test_notifier.py -q
```

[source: wiki/raw/runbook-symphony.md#128-134, wiki/raw/spec-review-brief-review-type-build-review-project-co.md]

## Notes / gaps

- Test bodies are not transcribed here. When a behaviour question lacks an answer in code/ADR/wiki, *grep the test* — test names are the most accurate behaviour catalogue Symphony has.
- No `conftest.py` was inspected; fixture conventions and `FakeTransport` shape are derivable from the test files themselves.
- The 2 `test_plane_adapter.py` tests are not a coverage gap; they are an architectural choice (adapter exercised via scheduler integration).

## Related

- [Scheduler loop](../concepts/scheduler-loop.md)
- [Blocked reconciler implementation](../concepts/blocked-reconciler-implementation.md)
- [Schedule comment grammar](../concepts/schedule-comment-grammar.md)
- [Agent runner + worktree](../concepts/agent-runner-and-worktree.md)
- [Prompt renderer](../concepts/prompt-renderer.md)
- [pi-swap review specs](pi-swap-review-specs.md) — codified the test-discipline contract
