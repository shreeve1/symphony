---
title: "Podium frontend deploy hazard + atomic deploy script + UI cosmetics"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - wiki/raw/sessions/2026-06-12-podium-frontend-deploy-and-ui-cosmetics.md
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

Recovery is a `sudo systemctl restart podium-web.service` (loads the new build cleanly) plus a browser **hard refresh** to drop stale cached HTML — **but only if a valid production `.next` exists on disk** (see next section).

## Second trigger: Playwright e2e clobbers the live `.next`

`pnpm test:e2e` → `playwright test`, whose `webServer` runs `next dev`. `next dev` writes a **development** `.next` (no `BUILD_ID`, dev chunk hashes) into the same `web/frontend/.next` that `podium-web.service`'s `next start` serves from. So running the frontend e2e suite against the repo dir silently overwrites the live production build [source: web/frontend/package.json, web/frontend/playwright.config.ts].

This is more dangerous than a plain in-place rebuild: while the original `next start` process keeps running it serves fine from its **in-memory** build, masking the damage. The breakage only surfaces on the *next* `podium-web` restart — `next start` then finds a dev `.next` with no `BUILD_ID`, errors `Could not find a production build in the '.next' directory`, and **crash-loops** (`auto-restart`, `NRestarts` climbing). Observed 2026-06-12: a `/dev-build` run executed `playwright test reply.spec.ts` at ~05:04, overwriting `.next`; the frontend kept serving until an unrelated `podium-web` restart ~07:51+ killed the good in-memory process and the service crash-looped. A simple restart could **not** recover it — only a fresh production build could.

Recovery from the crash-loop is `web/frontend/deploy.sh` (rebuilds a valid production `.next` via staging swap), not a bare restart. Prevention: do **not** run the frontend e2e suite against the live `web/frontend` dir during an automated build, or always finish such a build with `deploy.sh` to restore a clean production `.next`.

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
