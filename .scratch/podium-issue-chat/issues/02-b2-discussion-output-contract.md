# 02 — B2: Discussion output contract selection (coding bindings)

**What to build:** when `binding_type == "coding"`, dispatched prompts use the discussion contract (turn-taking, commit-as-you-go, no mandated marker); infra bindings keep `OUTPUT_CONTRACT` unchanged. Affects both full renders and resume deltas. No new column, no per-issue opt-in, no engine change.

**Blocked by:** None — independent of B1.

**Status:** ready-for-agent

- [ ] Select contract inside `render_prompt` based on `binding_type` parameter (already plumbed through `_render_candidate_prompt`)
- [ ] Add a `DISCUSSION_OUTPUT_CONTRACT` constant alongside the existing `OUTPUT_CONTRACT`
- [ ] Both code paths covered: full render at `prompt_renderer.py:465` and resume delta at `prompt_renderer.py:447`
- [ ] Coding-binding contract text: respond naturally to latest operator turn, invoke handed skill and follow it, commit-as-you-go, stop when the turn is said, emit terminal outcome only on skill-driven completion
- [ ] `SYMPHONY_RESULT` / `SYMPHONY_SCHEDULE` available but not mandated; `SYMPHONY_QUESTION` dropped (coding agent types the question in prose and stops)
- [ ] Engine / marker parser untouched (the existing parser stays in place; coding agents just don't invoke it)
- [ ] Infra binding path: zero change to the existing `OUTPUT_CONTRACT` text

Verification: `uv run pytest tests/test_prompt_renderer_podium.py -q`

Provenance: spec §9, §12.2; binding list per spec coding/infra split.

Wiki refs: [concepts/prompt-renderer.md].
