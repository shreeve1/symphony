# Session Capture: Retire context_md Re-feed Floor and Context Compaction

- Date: 2026-06-18
- Purpose: Retire the V1 Podium `context_md` prompt-memory re-feed floor and the automatic/manual context compaction that existed only to bound it. comments_md becomes the sole Symphony-managed prompt continuity surface; native CLI resume stays the memory path for resumed runs; `context_md` stays a dormant stored column for compatibility.
- Scope: Code changes that landed via `/dev-build plans/retire-context-md-refeed-floor.md`. Captures the new contract, what was removed, what was kept dormant, and verification.

## Durable Facts

- `context_md` is no longer injected into any Podium agent prompt. `prompt_renderer.render_prompt` dropped the non-resume `render_issue_context_block(issue.context_md)` block, and `render_issue_context_block` itself was deleted. — Evidence: `prompt_renderer.py`, `tests/test_prompt_renderer_podium.py`
- Automatic scheduler context compaction is removed: `scheduler/__init__.py` no longer has `_maybe_compact_context`, `SchedulerContextCompactionError`, the `from context_compaction import ...` line, or the `context-compaction-failed` block in dispatch. — Evidence: `scheduler/__init__.py`
- The manual compaction endpoint `POST /api/issues/{issue_id}/compact` and its `_compact_issue_context` helper were removed from `web/api/main.py`; POSTing the retired route now returns a client error (404/405). Orphaned imports removed with it: `context_compaction`, `build_binding_runtime`, `SymphonyConfig`, `_load_engine_main_for_legacy_app_dir`, `importlib.util`, `inspect`, `cast`. — Evidence: `web/api/main.py`, `web/api/tests/test_context_compaction.py`
- `context_compaction.py` and `tests/test_context_compaction.py` were deleted entirely. — Evidence: `git rm context_compaction.py tests/test_context_compaction.py`
- `PodiumTrackerAdapter.replace_context` and `PodiumTrackerAdapter.context_compaction_settings` were removed (compaction-only call sites). `append_context`/`_append_context` and low-level `context_md` persistence were KEPT — the scheduler still appends each run's output to `context_md` for continuity (not compaction). — Evidence: `tracker_podium.py`, `scheduler/__init__.py` (`append_context` call site)
- `context_md` remains a dormant STORED/SERIALIZED field: `IssueData.context_md` (`prompt_renderer.py`), the `context_md TEXT` column (`web/api/schema.py`), the tracker append/read path, and the `_render_candidate_prompt` passthrough (`main.py`) all stay. No schema-destructive migration was added; `binding_settings.context_compact_*` columns and Alembic revision `0002_context_compaction_settings` remain untouched (dormant). — Evidence: `web/api/schema.py`, `prompt_renderer.py`, `main.py`, `git diff` (no migration/schema file changed)
- `comments_md` remains the canonical Symphony-managed prompt continuity surface for non-resumed Podium dispatch; native CLI resume prompt behavior (output contract + newest operator reply only) is unchanged. — Evidence: `prompt_renderer.py`, `tests/test_dispatch_compaction.py`

## Decisions

- Keep `context_md` schema/column/field dormant for one compatibility window; defer physical schema cleanup to a later migration after an audit confirms no active consumers. — Evidence: `plans/retire-context-md-refeed-floor.md` (Notes)
- Keep the `compaction_agent_runner` parameter on dispatch functions as dormant plumbing rather than ripping it out, for minimal blast radius. — Evidence: `scheduler/__init__.py`, `tests/test_dispatch_compaction.py`
- Removal of the manual `/compact` route yields a 404/405 rather than a 410 handler; the test asserts route absence. — Evidence: `web/api/tests/test_context_compaction.py`

## Evidence

- `plans/retire-context-md-refeed-floor.md` — the executed plan (27/27 impl tasks, 12/12 tests complete).
- `plans/.retire-context-md-refeed-floor.state.yml` — build_audits: wave 1 pi audit `passed` (clean), wave 2 pi audit `audit_skipped`/`reviewer_timeout` (pi produced zero output and exited — the known pi-hang in this env; mitigated by an in-skill compatibility audit + full suite).
- Verification: `uv run pytest` → 917 passed, 2 skipped. Focused: `tests/test_prompt_renderer_podium.py tests/test_dispatch_compaction.py web/api/tests/test_context_compaction.py tests/test_tracker_podium.py web/api/tests/test_issue_patch.py` → 82 passed.
- `git diff --stat` → 10 files, +40 / −692.

## Exclusions

- No secrets read (`/home/james/symphony-host.env` untouched).
- No live service restart performed; changes are not yet committed.

## Open Questions And Follow-Ups

- Later migration to physically drop the dormant `context_md` column and `binding_settings.context_compact_*` columns after a compatibility window + a separate consumer audit.
- Decide whether the run-output append into `context_md` (`append_context`) should also be retired now that `context_md` is never re-fed to prompts (it currently still accrues run output for Session-tab/observability and dormant storage).
- Frontend/clients: no in-repo caller of `/compact` found other than the wiki/docs; external clients (if any) should be checked.
