# Handoff — Podium E2E troubleshooting on issue #389

## Why this exists

Issue #389 (file-viewer Maximize toggle) is **implemented, committed, deployed**.
A Playwright round-trip test for the new feature passes locally. While running the
full Playwright suite to make sure the new files route didn't regress anything,
**24 unrelated tests failed** with two distinct failure modes that are
**reproducible on baseline `main`** without my change. The operator needs a fresh
session to chase those down; they have another project to move on to.

## What is done (do NOT redo)

Commit `4672f1d` on local `main` (ahead of `origin/main` by 8 — confirmed pre-existing).

### Files touched
- `web/frontend/app/[binding]/files/page.tsx` — added `Maximize`/`Restore` toggle
  mirroring the IssueFlyout `toggleMaximized` pattern. Localstorage key
  `podium-files-expanded` (separate from `podium-flyout-maximized`). Tree pane
  hidden via `hidden` class but kept mounted.
  **As of 2026-07-15 follow-up**: unified into a single bottom-right control
  in both states — one `data-testid="files-expand-toggle"`, label flips
  Maximize ↔ Restore, position does not move. Tree-pane header h2 stripped
  back to the binding name with no Maximize button. Saves +38 LOC vs the
  previous split and removes the jumpy-position feel the operator reported.
- `web/frontend/tests/files.spec.ts` — added one round-trip test
  (`expand toggle hides tree, restores it, persists across reload`).

### Files NOT touched (but appear in `git status`)
- `web/api/tests/test_files.py` — pre-existing Python reformat of one param split
  onto two lines, **not authored by me**. Leave alone.

### Verified working
- `./node_modules/.bin/tsc --noEmit` (from `web/frontend`) — passes.
- `./node_modules/.bin/playwright test files.spec.ts --reporter=list` (full path,
  cwd = `web/frontend`): both tests green in ~17.5s. **Critical**: run from
  `web/frontend`, not the repo root, or `playwright.config.ts` doesn't find the
  test dir.
- `uv run pytest web/api/tests/test_files.py -q` — 20/20 pass.
- `./deploy.sh` — atomic frontend rebuild + `podium-web` swap succeeded; service
  `active` after, `curl /homelab/files` → 200. **`podium-api` and `symphony-host`
  were never touched.**

## The unresolved failure cluster

Running the **full Playwright suite** from `web/frontend`:

```
timeout 480 ./node_modules/.bin/playwright test --reporter=list
→ 50 passed, 24 failed
```

### Two distinct failure modes

**Mode A — `uv` spawn failure inside `runDbScript`** (`web/frontend/tests/fixtures.ts:89`):
```
TypeError: apiRequestContext.post: Invalid URL
  at web/frontend/tests/fixtures.ts:26 (authenticate)
  at runDbScript (.../fixtures.ts:89) — execFileSync("uv", ["run", "python", "-c", script])
```
Hits tests that seed DB rows via the helper, e.g. `inbox.spec.ts:154`,
`new-issue.spec.ts:*`, `dependency-chip.spec.ts:11`, `editing.spec.ts:27`,
`schedule.spec.ts:*`, `session-tail.spec.ts:29`, `skill-catalog.spec.ts:3`,
`steer-flyout.spec.ts:*`, `console.spec.ts:11`, `live-sync.spec.ts:*`.

**Mode B — missing `getByTestId('issue-flyout')` after the seeded reply**:
```
Error: element(s) not found
Call log:
  - waiting for getByTestId('issue-flyout')
```
`inbox.spec.ts:178` — after a successful reply the flyout stays open per spec,
but it's not there. Likely the same Mode A under the surface: the seed row never
landed, so the operator-reply mutation had nothing to flip, and the page navigated
away.

### Confirmed pre-existing (NOT my change)

```bash
git stash push -m "files-page-toggle" \
  -- web/frontend/app/[binding]/files/page.tsx web/frontend/tests/files.spec.ts
cd web/frontend && ./node_modules/.bin/playwright test inbox.spec.ts:154 \
  --reporter=list
# Same failure on baseline.
git stash pop
```

Reproduction done on 2026-07-15. The 24 failures on the `files.spec.ts` testbed
match the failures on `main` HEAD.

### Hypotheses (ranked)

1. **`uv` is missing from PATH or shadowed** in this shell session. Tests do
   `execFileSync("uv", ...)` from `cwd: path.resolve(__dirname, "../../..")`,
   i.e. the repo root, with explicit `PODIUM_DB_PATH` env. If `uv` isn't on the
   inherited PATH for the Playwright child process, every seed fails and every
   test that depends on a seeded row trips Mode A. Cheap first check:
   `which uv && uv --version` from both repo root and from `web/frontend/`.
2. **The fixtures' Python subprocess script has stale assumptions.** It does
   `from web.api.db import connect` + `from web.cli.podium_skills import
   ensure_schema`. If the e2e DB path or any env var moved since the fixtures
   were authored, the subprocess returns non-zero and is reported as Mode A's
   upstream. Quick check: from the repo root,
   `uv run python -c "from web.api.db import connect"`.
3. **The baseline failures pre-date #389 but were never noticed.** Confirm with
   `git log --oneline web/frontend/tests/inbox.spec.ts | head` and ask whether a
   recent slice changed any fixtures.

## Where to start the next session

Suggested order (smallest first, cheapest signal):

1. **Sanity**: `which uv; which node; node --version; pnpm -v`. If `uv` is
   missing or below the version in `pyproject.toml`, install it
   (`pipx install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. **Re-run the full Playwright suite from `web/frontend`** with a clean
   `test-results/` first: `rm -rf web/frontend/test-results/podium-e2e.db
   web/frontend/test-results/pi-sessions web/frontend/test-results/e2e-repos`
   then the same `./node_modules/.bin/playwright test --reporter=list`. Compare
   the failure list. If it shrinks, leftover state was the cause; if it's the
   same 24, it's the python/uv path.
3. **Manually run one seed path outside Playwright**: from repo root,
   `PODIUM_DB_PATH=$(pwd)/web/frontend/test-results/podium-e2e.db
    PI_CODING_AGENT_SESSION_DIR=$(pwd)/web/frontend/test-results/pi-sessions
    PODIUM_BINDINGS_PATH=$(pwd)/web/frontend/test-results/e2e-bindings.yml
    uv run python -c "from web.api.db import connect; connect()"` — does
   this succeed? If not, that's the failure mode and the fix is upstream.
4. **If `uv` is the bottleneck**, check whether the test rig itself installed
   `uv` into the shell's PATH or relied on a venv. The fix is usually making
   the PATH explicit in the helper or installing `uv` into a known location.
5. **Only after all 24 are green**, run `files.spec.ts` once more to confirm
   2/2 green.

## Critical environment notes

- **Run Playwright from `web/frontend` cwd**, not repo root. `playwright.config.ts`
  uses `testDir: "./tests"` which is relative.
- **Use full binary paths**. The shell between turns resets cwd back to the repo
  root, and relative `./node_modules/.bin/playwright` will silently fail.
  Absolute path: `/home/james/symphony/web/frontend/node_modules/.bin/playwright`.
- **`pnpm exec playwright ...` does NOT work** — corepack triggers an `install`
  side effect that errors on the repo root because there's no `package.json`
  there. Use the absolute path.
- **`./deploy.sh`** targets `podium-web.service` ONLY. The atomic swap leaves
  `.next.prev/` for rollback. `podium-api` and `symphony-host` are untouched.
- **Don't touch `wiki/`** for this issue — this is a Podium slice run, exempt
  from per-slice wiki updates per ADR-0028.

## Pointers to existing artifacts (do not duplicate)

- Commit `4672f1d` — full diff of the initial #389 toggle implementation.
- Commit `d304da3` — placement follow-up: unified Maximize/Restore into one
  bottom-right control (response to operator feedback that the two
  placements felt inconsistent).
- `web/frontend/app/[binding]/files/page.tsx` — current source of truth.
- `web/frontend/tests/files.spec.ts` — current source of truth for the test.
- `web/frontend/deploy.sh` — atomic Podium frontend deploy, comments explain
  the stop→swap→start sequence.
- `web/README.md` — when each service needs a restart.
- `wiki/concepts/symphony-operations.md`, `wiki/analyses/podium-frontend-deploy-cosmetics.md`
  — prior deploy hazards (stale webpack `.next/cache`, restart-cancel race).

## Suggested skills for the next session

- **`diagnose`** — disciplined reproduce → minimise → hypothesise → instrument
  → fix → regression-test loop. Best fit for the 24-failure cluster because the
  signal-to-noise is poor and the surface area is wide.
- **`dev-test`** — once a root cause is narrowed, for backfilling a focused
  regression fixture or tightening an existing one.
- **`grill-me`** — only if the operator returns with a design question (e.g. "do
  we want a per-binding localStorage key for the file toggle?"). Not the right
  tool here — this is now a debugging task, not a design one.
- **NOT `autoagent`** — this is a runtime/environment failure with many
  independent signals, not a hill-climb test problem. Don't burn CPU iterating.
- **NOT `ponytail-review` / `ponytail-audit`** — there's nothing to delete.

## Open questions for the operator (only if needed)

- Was the 24-failure cluster known and accepted as long-standing flake before
  #389, or is this the first time the operator noticed it?
- Is `uv` installed system-wide, or does the test rig shell only see it via
  corepack-style shimming?
- Are there any further builds planned for tonight, or is the next maintenance
  window the right place to chase these down?
