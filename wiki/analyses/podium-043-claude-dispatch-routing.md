---
title: "#043 Claude dispatch routing"
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - .kanban/issues/043-wire-claude-dispatch.md
  - agent_runner.py
  - main.py
  - scheduler.py
  - tests/test_agent_runner.py
  - tests/test_dispatch_gate.py
  - tests/test_dispatch_compaction.py
  - tests/test_trading_podium_dispatch.py
confidence: high
tags: [podium, dispatch, claude, routing, ralph]
---

# #043 Claude dispatch routing

Issue #043 wires the #042 tmux-backed Claude adapter into real Podium dispatch routing. Claude Issues are no longer blocked solely because the resolved agent is non-Pi; the dispatch gate now accepts matching Claude catalog entries and annotates the candidate with `resolved_provider=""` plus the bare model id [source: .kanban/issues/043-wire-claude-dispatch.md] [source: scheduler.py] [source: tests/test_dispatch_gate.py]. Pi dispatch remains the legacy-shaped branch: provider comes from the model entry and `reasoning_effort` appends to the model id as `:<effort>` [source: scheduler.py] [source: tests/test_dispatch_gate.py].

## Routing and runtime construction

`RoutingAgentAdapter` now carries both `pi_adapter` and `claude_adapter`; each call resolves the Issue agent from binding labels and routes to the matching adapter [source: agent_runner.py]. `main._build_binding_runtime(...)` constructs `ClaudeAgentAdapter` alongside `PiAgentAdapter`, while retaining the Pi adapter separately so engine housekeeping can bypass Claude when needed [source: main.py]. Tests cover a single binding routing an unlabeled/Pi Issue to the Pi fake and an `agent:claude` Issue to the Claude fake [source: tests/test_agent_runner.py].

## Run row fields

For non-Pi agents, `_start_run_record(...)` stores `resolved_provider` and `resolved_model` verbatim instead of falling back to `config.pi_provider` or `config.pi_model` [source: scheduler.py]. Claude Run rows therefore record `agent="claude"`, `provider=""`, and a suffix-free model such as `claude-opus-4-8` [source: tests/test_trading_podium_dispatch.py]. This preserves Run-row honesty: stored fields match what the Claude adapter receives in `issue.resolved_model` [source: tests/test_trading_podium_dispatch.py].

## Post-run parsing

Claude result-file stdout is authoritative for `SYMPHONY_RESULT`, `SYMPHONY_SUMMARY`, permission gates, and approval gates. Pane stderr is diagnostics only because it can echo the pasted prompt, including marker vocabulary and phrases like `approval required` [source: scheduler.py]. Pi keeps the historical stdout+stderr parsing path [source: scheduler.py]. The regression test sends a Claude-shaped result with clean markerless stdout plus pane stderr containing `approval required` and a bogus `SYMPHONY_SUMMARY:`; the run lands in review, stores no bogus summary, and does not trip the approval gate [source: tests/test_trading_podium_dispatch.py].

Markerless non-empty Claude stdout still lands the scheduler default `review` verdict, preserving parity with the Pi path and #042's markerless-success contract [source: scheduler.py] [source: tests/test_trading_podium_dispatch.py].

## Context compaction stays Pi-only

Context compaction remains engine housekeeping, not part of the operator's selected agent run. `run_tick(...)` accepts a `compaction_agent_runner`; `main.run_bindings_loop(...)` passes the Pi adapter there even when the operator dispatch routes through `RoutingAgentAdapter` [source: scheduler.py] [source: main.py]. `_maybe_compact_context(...)` resolves the Pi catalog default and calls compaction with Pi-shaped resolved fields before the real operator dispatch uses the Issue's own Claude fields [source: scheduler.py]. The compaction regression test asserts a Claude-labeled over-threshold candidate compacts through the fake Pi adapter with `openai-codex/gpt-5.5:high`, then dispatches through the fake Claude adapter with `provider=""` and `claude-opus-4-8` [source: tests/test_dispatch_compaction.py].

## Verification

Ralph verification for #043 passed `git diff --check`, `uv run pytest -q` (681 passed, 1 skipped), touched-file LSP diagnostics for changed Python files, and a fresh read-only Ralph review against base commit `740d25ba26155e60d4a399d7bddb05d49981ffc3` with result `RALPH_REVIEW: PASS` [source: .kanban/issues/043-wire-claude-dispatch.md].
