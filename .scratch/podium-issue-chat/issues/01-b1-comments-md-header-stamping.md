# 01 — B1: `comments_md` write-side header stamping

**What to build:** every new write into `comments_md` lands with a uniform machine-parseable header `### <role> · <ISO-ts>Z` (roles: agent | operator | patrol | system). Legacy pre-headered content is untouched (no backfill); new writes get stamped at write time. The `/comment` endpoint lightly bends ADR-0017's "verbatim" wording by adding an attribution wrapper around the operator's verbatim body — flagged for ADR cross-check in the issue comment.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] One shared `_stamp_comment(role, body, ts)` helper accepts the role as a parameter
- [ ] Scheduler `add_comment` paths (~17 sites) stamp `agent` for agent turns, `patrol` for patrol-originated comments
- [ ] `POST /api/issues/{id}/comment` stamps `operator` unconditionally (the body is still verbatim; only the wrapper changes)
- [ ] `/reply` stamps `operator`; `/steer` stamps `operator` (with steer/abort badge carried via role-style header for now); `### Symphony AI Summary`, `### Symphony Review`, `Symphony-Schedule:` marker, `### Symphony Retry Epoch` normalize onto the §2.1 grammar
- [ ] `_capture_natural_turn` strips agent-emitted SYMPHONY_ markers before write (existing behaviour preserved)
- [ ] Regex `^### (agent|operator|patrol|system) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$` matches every newly-stamped block
- [ ] Old-format headers (`### Operator Reply (`, `### Symphony`, `Symphony-Schedule:`) are NOT rewritten; no destructive migration
- [ ] Test updated: `test_comment_appends_verbatim_without_header` reflects the new attribution header
- [ ] All 11 read/write paths over `comments_md` continue to work with no DB migration

Verification: `uv run pytest web/api/tests/test_comment.py web/api/tests/test_reply.py tests/test_scheduler.py -q`

Provenance: spec §2, §2.1, §2.2, §2.3, §12.1; ADR-0017 lightly bent (recorded in issue comment).

Wiki refs: [concepts/operator-reply.md], [concepts/podium-tracker.md].
