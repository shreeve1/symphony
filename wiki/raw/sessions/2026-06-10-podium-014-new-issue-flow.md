# Session Capture: Podium #014 new-issue flow — implementation, review, modal evolution

- Date: 2026-06-10
- Purpose: Implemented kanban issue #014 (Podium "file a new issue"), ran an independent dev-review-claude pass and addressed all nine findings, then applied three operator-requested UI changes to the flyout and new-issue modal.
- Scope: Endpoint/modal contract decisions, review findings and resolutions, operator UI preferences, and cross-slice constraints for #015 and #020. No transcript, no secrets, no `/home/james/symphony-host.env` content.

## Durable Facts

- `POST /api/bindings/{name}/issues` creates a Todo issue with server defaults `state='todo'`, `worktree_active=false`; `reasoning_effort` defaults to `'high'` and `base_branch` to the binding's `bindings.yml` entry, but both are client-settable since `a6157f3`. `state` in the body is 400; invalid values 422; unknown binding 404 (checked before body validation, pinned by `test_create_unknown_binding_beats_body_validation`). — Evidence: `web/api/main.py` (`IssueCreate`, `create_binding_issue`), `web/api/tests/test_issue_create.py`
- Skill seeding switched from insert-if-table-empty to per-row `INSERT OR IGNORE` and gained `/diagnose`, because the #014 acceptance criterion (`preferred_skill: "/diagnose"` → 201) collided with the `preferred_skill` FK + `PRAGMA foreign_keys = ON` and the old seed catalog. — Evidence: `web/api/seed.py` (`_seed_skills`, `SEED_SKILLS`), commit `a68cccf`
- `GET /api/bindings/{name}/options` feeds the new-issue dropdowns: `agents` is static `["pi", "claude"]` mirroring the scheduler's `_validate_agent` set (`config.py:471`); `models` is the curated placeholder `KNOWN_MODELS` list (no real model catalog exists anywhere in Symphony); `branches` is read live via `git for-each-ref refs/heads` from the binding's `repo_path` in `bindings.yml`, degrading to `[]` on any failure. — Evidence: `web/api/main.py` (`binding_issue_options`, `_branches_for`), commit `bf7cfd0`
- New-issue modal submits optimistically (temp card with negative id prepended to the `["issues", binding]` cache) but closes only on POST success; on failure the temp card rolls back, the modal stays open with an error line and the typed values intact. Submit is disabled while the mutation is pending. — Evidence: `web/frontend/components/NewIssueModal.tsx`, `web/frontend/tests/new-issue.spec.ts` (failure-path spec), commit `f0de67b`
- `_base_branch_for` guards `OSError`/`yaml.YAMLError` from the request-time `bindings.yml` read and falls back to `'main'` instead of 500ing issue creation. — Evidence: `web/api/main.py`, `test_create_falls_back_to_main_when_bindings_yml_unreadable`
- `issue.preferred_agent` / `preferred_model` are free text (no enum/FK validation at create or patch); only `preferred_skill` is FK-checked. — Evidence: `web/api/main.py` (`IssueCreate`, `IssuePatch`), note appended to `.kanban/issues/020-podium-trading-cutover.md`
- Playwright specs deliberately write to the persistent dev database: editing.spec mutates the `/homelab` seeds, new-issue.spec appends one Todo card per run. Seed skills only appear after an API process restart (seeding runs in the FastAPI lifespan). One transient parallel-run flake observed when editing.spec and new-issue.spec hit `/homelab` concurrently. — Evidence: `web/README.md` (e2e section), e2e run logs this session
- Dev loop on aidev: uvicorn `--reload` on `127.0.0.1:8090`, `next dev` on `8091`; both pick up code changes without manual restarts (uvicorn reload re-runs lifespan seeding).

## Decisions

- James: flyout drops the `priority` select and `max s` (max_duration_seconds) number chip; backend PATCH support for both fields stays, priority badge stays on board cards. — Evidence: commit `4aab377`
- James: new-issue modal carries all flyout-editable fields as optional inputs (skill, agent, model, effort, worktree, base branch) and drops priority entirely from the modal; omitted fields take server defaults. This loosened the API: `reasoning_effort` and `base_branch` were previously rejected as server-set (400), now accepted. — Evidence: commit `a6157f3`
- James: agent, model, and base branch are dropdowns, not free text, on the new-issue modal — hence the `/options` endpoint. — Evidence: commit `bf7cfd0`
- James: "address all" on the nine dev-review-claude findings — including modal error surfacing (spec deviation from #014's "close modal on submit"), bindings.yml read guard, 404-precedence test, seed-resurrection note in #015, free-text agent/model note in #020, e2e dev-DB note in `web/README.md`. — Evidence: commit `f0de67b`, `.kanban/issues/015-podium-skill-catalog.md` Notes, `.kanban/issues/020-podium-trading-cutover.md` Notes

## Evidence

- Commits (all local, unpushed at capture time): `a68cccf` (#014 implementation), `f0de67b` (review findings), `4aab377` (flyout chip removal), `a6157f3` (modal flyout-parity), `bf7cfd0` (options endpoint + dropdowns).
- `web/api/tests/test_issue_create.py` — endpoint contract: defaults, precedence, bindings.yml fallback, options endpoint (incl. tmp-git-repo branch listing).
- `.kanban/issues/014-podium-file-new-issue.md` — spec; status flipped to done this session.
- Test state at capture: 486 pytest, 9 Playwright, all green.

## Exclusions

- No `/home/james/symphony-host.env` values or any secrets.
- Full conversation transcript not archived.
- Reviewer tmux session internals (dev-review-claude engine temp files) — transient, not project knowledge.

## Open Questions And Follow-Ups

- #015 must retire `SEED_SKILLS`/`_seed_skills` or take ownership of the `skill` table; `INSERT OR IGNORE` at boot resurrects deleted seed rows and never rewrites changed descriptions.
- `KNOWN_MODELS` in `web/api/main.py` is a hand-curated placeholder; revisit when a real model catalog source exists.
- #020 dispatch must handle free-text `preferred_agent`/`preferred_model` gracefully (fall back to binding `default_agent` / configured model).
- e2e flake risk: editing.spec and new-issue.spec both target `/homelab` in parallel; if recurrence, serialize them or give new-issue its own binding.
- Commits unpushed to `github-personal` at capture time.
