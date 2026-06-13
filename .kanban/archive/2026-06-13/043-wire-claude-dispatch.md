---
id: 043
title: Wire claude dispatch end-to-end through gate, routing, and verdict parsing
status: done
blocked_by: [041, 042]
parent: null
priority: 1
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

Connect #042's `ClaudeAgentAdapter` behind #041's agent-aware gate so an issue with `preferred_agent=claude` dispatches for real, per the ADR-0001 amendment (`docs/adr/0001-claude-via-tmux-send-keys.md`). Pi path behavior must be byte-for-byte unchanged.

Changes:

1. `scheduler.py` `_apply_dispatch_gate` — remove the `agent != "pi"` "engine is not wired" block and the wired-agent restriction on the model entry (the #041 mismatch check `entry["agent"] != agent` stays). Branch the resolved fields by agent: pi keeps `resolved_provider=str(entry["provider"])` and `resolved_model=f"{entry['id']}:{effort}"`; claude sets `resolved_provider=""` and `resolved_model=entry["id"]` (bare id — no provider key exists on claude entries, no `:effort` suffix ever).
2. `agent_runner.py` `RoutingAgentAdapter` — add a `claude_adapter: AgentAdapter` field; `__call__` resolves the agent per call via `self.binding.resolve_agent(issue.labels)` and routes to the matching adapter. Construction sites (grep for `RoutingAgentAdapter(`) build the claude adapter alongside the pi adapter.
3. `scheduler.py` `_start_run_record` — store provider verbatim from `resolved_provider` for non-pi agents: the `or config.pi_provider` fallback must apply only when the agent is pi. Claude Run rows carry `agent="claude"`, empty provider, bare model id.
4. `scheduler.py` post-run parsing — for claude runs, verdict marker, summary marker, and the permission/approval gate regexes (`_hit_permission_gate`, `_hit_approval_gate`, `_parse_summary_marker`) operate on `result.stdout` (the result-file content) ONLY, never on `result.stderr` (the pane capture echoes the pasted prompt, which quotes the marker vocabulary and may contain phrases like "approval required" that would falsely trip `_APPROVAL_GATE_RE`). Pi runs keep scanning stdout+stderr exactly as today. Key the branch on the agent resolved for the run (already available where the Run row is recorded).
5. **Context compaction stays pi-only.** `_maybe_compact_context` currently receives the dispatch `agent_runner`, and `maybe_compact` parses `result.stdout` as the compacted context (`context_compaction.py:68,78`) — routing a claude issue's compaction through the tmux adapter would wrap Symphony's compaction prompt in the claude completion-contract preamble and corrupt the output. Compaction is engine housekeeping: it always runs through the pi adapter with the pi catalog default model (`resolve_model(None, models, agent="pi")`), regardless of the issue's resolved agent. Pass the pi adapter (not the routing adapter) into the compaction call site and override the candidate's resolved provider/model with the pi defaults for that call only — the dispatch that follows still uses the issue's own agent/model.
6. Update gate tests: claude agent + claude model passes the gate with `resolved_provider=""` and suffix-free `resolved_model`; pi agent + pi model output is unchanged (`:effort` suffix intact); mismatches still block.

## Acceptance criteria

- [x] Scheduler-level test: candidate with `agent:claude` label + claude model dispatches through a fake claude adapter (no "engine is not wired" block) and records a Run row with `agent="claude"`, `provider=""`, `model="claude-opus-4-8"`.
- [x] Pi dispatch regression: existing pi gate/dispatch tests pass without modification of their expected argv/fields (`:high` suffix and provider intact).
- [x] `RoutingAgentAdapter` test: same binding, one issue labeled `agent:claude` and one `agent:pi`, routed to the respective fake adapters.
- [x] Claude run whose stderr (pane) contains "approval required" and a bogus `SYMPHONY_SUMMARY:` line, but whose stdout (result file) is clean, does NOT trip the approval gate and takes its summary from stdout. Equivalent pi-shaped run still trips the gate (stderr still scanned for pi).
- [x] Claude run with non-empty markerless stdout lands the default `review` verdict (parity with pi).
- [x] Compaction test: a claude-labeled candidate over the compaction threshold compacts via the pi adapter with the pi default model (assert the fake pi adapter received the call and the fake claude adapter did not), and the subsequent dispatch still routes to the claude adapter.
- [x] `uv run pytest` green.

## Verification

`uv run pytest`

## Implementation Notes

- Removed the non-pi dispatch gate block while keeping agent/model mismatch validation.
- Added Claude routing to `RoutingAgentAdapter` and runtime construction.
- Stored Claude run provider/model fields verbatim (`provider=""`, bare model id).
- Restricted Claude post-run verdict, summary, permission, and approval parsing to stdout only; Pi keeps stdout+stderr parsing.
- Kept context compaction on the Pi adapter with the Pi catalog default before subsequent Claude dispatch.
- Verification passed: `uv run pytest` (681 passed, 1 skipped). Fresh Ralph review passed.

## Blocked by

- Blocked by #041
- Blocked by #042
