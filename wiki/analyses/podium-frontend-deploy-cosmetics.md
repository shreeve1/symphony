---
title: "Podium frontend deploy hazard + atomic deploy script + UI cosmetics"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-29
sources:
  - wiki/raw/sessions/2026-06-12-podium-frontend-deploy-and-ui-cosmetics.md
  - wiki/raw/sessions/2026-06-15-podium-web-stale-build-client-exception.md
  - wiki/raw/sessions/2026-06-29-gfm-table-renderer-and-deploy-stale-cache.md
  - web/frontend/deploy.sh
  - web/frontend/next.config.mjs
  - web/frontend/playwright.config.ts
  - web/frontend/package.json
  - web/frontend/components/AppShell.tsx
  - web/frontend/components/IssueCard.tsx
confidence: high
tags: [podium, frontend, deploy, next-start, next-build, sidebar, issue-card, operations]
---

# Podium frontend deploy hazard + atomic deploy script + UI cosmetics

## Context

A cosmetic frontend change request (collapsible left sidebar, simplified issue-card quick-view) surfaced a latent deploy hazard in how the Podium frontend is built and served, which was root-caused and fixed during the same session.

## Root cause: in-place rebuild under live `next start`

`podium-web.service` runs `pnpm start -p 8091` → `next start -H ${HOST:-0.0.0.0} -p 8091` [source: wiki/raw/sessions/2026-06-12-podium-frontend-deploy-and-ui-cosmetics.md#durable-facts]. This serves a **prebuilt** `.next` and never hot-reloads, so source edits need a rebuild + restart to appear.

`next build` overwrites `.next` in place. While the old server keeps serving the previous in-memory HTML (which references the old chunk hashes), the on-disk static chunks have new hashes, so asset requests in that window 400 with `text/html` MIME — the browser refuses the stylesheet/script and the app hangs at "Checking session…". Observed live: the served HTML referenced `296af0bbdbe2ffd4.css` while the disk had rebuilt to `47857b3ee08e2d46.css` [source: wiki/raw/sessions/2026-06-12-podium-frontend-deploy-and-ui-cosmetics.md#durable-facts].

**Live recurrence 2026-06-15 (C-0213).** This hazard recurred in production: a bare `next build` ran against the live `web/frontend` dir (bypassing `deploy.sh`) ~3h after `podium-web` boot (server up 2026-06-14 23:43:01, `.next` rebuilt 02:24). The symptom this time was the browser **"Application error: a client-side exception has occurred (see the browser console for more information)"** — a React hydration failure, distinct from the "Checking session…" hang above but the same root cause: the served HTML referenced old app-router chunk hashes (`app/[binding]/page-d526ae8…js`, `app/layout-124a785…js`) that the rebuild had renamed on disk (to `page-ece4dea…js`, `layout-e593ac…js`), so those requests 400'd. `sudo systemctl restart podium-web.service` **alone** fixed it (the 02:24 build was already valid on disk; only the in-memory manifest was stale) — all 11 served chunks returned 200 afterward. So the in-place-rebuild symptom catalogue now includes both a stylesheet/script-MIME 400 hang *and* an app-router-chunk-400 client-side exception [source: wiki/raw/sessions/2026-06-15-podium-web-stale-build-client-exception.md#durable-facts].

Recovery is a `sudo systemctl restart podium-web.service` (loads the new build cleanly) plus a browser **hard refresh** to drop stale cached HTML — **but only if a valid production `.next` exists on disk** (see next section).

## Second trigger: Playwright e2e clobbers the live `.next`

`pnpm test:e2e` → `playwright test`, whose `webServer` runs `next dev`. `next dev` writes a **development** `.next` (no `BUILD_ID`, dev chunk hashes) into the same `web/frontend/.next` that `podium-web.service`'s `next start` serves from. So running the frontend e2e suite against the repo dir silently overwrites the live production build [source: web/frontend/package.json, web/frontend/playwright.config.ts].

This is more dangerous than a plain in-place rebuild: while the original `next start` process keeps running it serves fine from its **in-memory** build, masking the damage. The breakage only surfaces on the *next* `podium-web` restart — `next start` then finds a dev `.next` with no `BUILD_ID`, errors `Could not find a production build in the '.next' directory`, and **crash-loops** (`auto-restart`, `NRestarts` climbing). Observed 2026-06-12: a `/dev-build` run executed `playwright test reply.spec.ts` at ~05:04, overwriting `.next`; the frontend kept serving until an unrelated `podium-web` restart ~07:51+ killed the good in-memory process and the service crash-looped. A simple restart could **not** recover it — only a fresh production build could.

Recovery from the crash-loop is `web/frontend/deploy.sh` (rebuilds a valid production `.next` via staging swap), not a bare restart. Prevention: do **not** run the frontend e2e suite against the live `web/frontend` dir during an automated build, or always finish such a build with `deploy.sh` to restore a clean production `.next`.

## Third trigger: stale webpack cache → byte-identical bundle ships old code

Distinct from the two hazards above (in-place rebuild MIME 400; Playwright `next dev` crash-loop). `deploy.sh` only `rm -rf`s the staging dist dir (`.next.staging`), never `.next/cache`. Next.js keeps a **persistent webpack cache** at `.next/cache`; a rebuild can reuse stale cached modules and emit a **byte-identical page bundle that carries none of the source edits** [source: web/frontend/deploy.sh, wiki/raw/sessions/2026-06-29-gfm-table-renderer-and-deploy-stale-cache.md#third-deploy-hazard].

Observed 2026-06-29 (C-0347): the GFM-table renderer fix. First `deploy.sh` run reported success (`is-active` + root 200), but the `[binding]` page bundle stayed `page-ae8e2ada9e8d7983.js` dated 2026-06-26 with **identical md5 in both `.next` and `.next.prev`** — the `Markdown.tsx` edit never shipped. Because the bundle filename was unchanged and chunks are served `Cache-Control: public, max-age=31536000, immutable`, the browser cache-hit and kept rendering the old table-as-text. This was proven server-side, not a client-cache problem: the served live chunk md5 equalled the on-disk md5 both times, but the *first* run's bundle genuinely lacked the edit (no `gfmTable` marker).

Recovery: `rm -rf .next/cache .next.staging` then `deploy.sh` → fresh bundle with a new content hash (`page-dd17ba642575253a.js`, dated today) carrying the change. **Prevention (unfixed in `deploy.sh` as of 2026-06-29): `rm -rf .next/cache` before `pnpm build`.**

Diagnostic shortcut for the next occurrence: after a deploy that "looks successful" but the UI didn't change, compare the page-bundle filename/md5 across `.next` and `.next.prev` and grep the live-referenced client chunk for a marker unique to the edit. Identical md5 + missing marker = stale cache, not a browser-cache issue.

## deploy.sh restart-cancel race

`deploy.sh` does `sudo systemctl stop` then immediately `sudo systemctl start`. `stop` returns before the unit has fully released; `start` hits a still-`deactivating (final-sigterm)` unit and returns `Job for podium-web.service canceled.`, leaving the service **DOWN** until manually waited out (the `deactivating` linger exceeded 20s on 2026-06-29) and re-started [source: web/frontend/deploy.sh (lines 30/34), wiki/raw/sessions/2026-06-29-gfm-table-renderer-and-deploy-stale-cache.md#deploy-sh-restart-cancel-race].

Recovery: poll `systemctl is-active` until it reports `inactive`/`failed`, then `sudo systemctl start`. The clean second deploy (post cache-bust) did **not** reproduce it, so the race is timing-dependent but real — `deploy.sh` cannot be assumed to leave the service up just because `is-active` passed the verify step (the canceled-start case never reaches a healthy `active`). **Prevention (unfixed): poll `is-active` through `deactivating` before issuing `start`, or retry `start` on cancel.**

## Fix: atomic staging-swap deploy

Chosen prevention (Option A) keeps the live site up through the slow build, then does a fast atomic swap:

1. `next.config.mjs` gains `distDir: process.env.NEXT_DIST_DIR ?? ".next"` — default unchanged, lets a build target a staging dir [source: web/frontend/next.config.mjs].
2. `web/frontend/deploy.sh` builds into `.next.staging` (live `.next` untouched during the build), restores the build-mutated `tsconfig.json`, then `sudo systemctl stop` → swap `.next` (old kept as `.next.prev`) → `start`, then verifies `is-active` + root 200. Rollback: `mv .next .next.bad && mv .next.prev .next && sudo systemctl restart` [source: web/frontend/deploy.sh].
3. `.gitignore` ignores `.next.staging` / `.next.prev`.

Why atomic swap over a bundled `pnpm build && restart`: the failure window is the *build* itself (live `.next` overwritten in place); building to staging removes that window entirely, leaving only the ~3s stop/swap/start. Note `next build` also rewrites `tsconfig.json` (array reformat + transient `<distDir>/types` include) — machine noise the script reverts.

Validated build-only at first capture; **first real end-to-end run 2026-06-12**: `deploy.sh` recovered the frontend from the `next dev` crash-loop above — staging build compiled, `tsconfig.json` churn auto-reverted (tree clean after), stop/swap/start completed, `is-active` + root 200 verified, and the previously-400ing chunks (`904e0d82087b0725.css`, `webpack-*.js`) returned 200 with correct MIME. The stop/swap/start path is now proven.

## UI cosmetic decisions (operator-requested)

- **Collapsible sidebar**: top-left `PanelLeft` toggle in the header; open/closed persisted to `localStorage` key `podium:sidebar-open`; `Sidebar` conditionally rendered [source: web/frontend/components/AppShell.tsx].
- **Card quick-view simplified**: dropped `PriorityBadge` (low/med/high) and `VerdictPill` (done/review/blocked — duplicated the column); now shows a colour-coded agent pill (`claude`=orange, `pi`=violet) from `issue.preferred_agent` plus `issue.preferred_model`, falling back to "default agent" when neither is pinned. Age retained. `badges.tsx` exports kept — still used by `RunHistoryList` [source: web/frontend/components/IssueCard.tsx].

The card reads the issue's *pinned preference* (`preferred_agent`/`preferred_model`), not the last Run's actual agent/model — those live on the `run` table, not the issue-list payload (see C-0058). Showing the real run agent/model would require a new field on the list endpoint.

## Follow-ups

- Commit the five working-tree changes (latest commit at capture: `eef75d1`). (Done.)
- ~~First real `deploy.sh` run will exercise stop/swap/start live.~~ Done 2026-06-12 (see Fix section).
- Isolate frontend e2e from the live build dir: point Playwright's `webServer` / `NEXT_DIST_DIR` at a throwaway dir, or gate `test:e2e` out of automated `/dev-build` runs, so a test run can never overwrite the production `.next` that `podium-web` serves. Until then, any build that runs `playwright test` must end with `deploy.sh`.
- **Patch `deploy.sh` to `rm -rf .next/cache` before `pnpm build`** (third-trigger prevention, C-0347, unfixed as of 2026-06-29).
- **Patch `deploy.sh` restart to be self-healing** (poll `is-active` through `deactivating` before `start`, or retry `start` on cancel) so a timing-canceled start cannot leave `podium-web` down (unfixed as of 2026-06-29).
- Add a Playwright regression lock: a comment containing a GFM table renders a `<table>` (`flyout-tabs.spec.ts` doesn't cover tables today).
- Commit the three GFM renderer working-tree changes (`Markdown.tsx`, `package.json`, `pnpm-lock.yaml`).
