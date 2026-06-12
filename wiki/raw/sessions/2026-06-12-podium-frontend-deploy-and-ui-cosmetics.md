# Session Capture: Podium frontend deploy hazard + atomic deploy script + UI cosmetics

- Date: 2026-06-12
- Purpose: Cosmetic frontend changes (collapsible sidebar, card quick-view) exposed a deploy hazard — rebuilding `.next` in place under a live `next start` broke the served site — which was root-caused and fixed with an atomic staging-swap deploy script.
- Scope: Captured the deploy root cause + procedure and the operator-requested UI decisions. Excludes transcript, secrets, and routine progress chatter.

## Durable Facts

- `podium-web.service` runs `pnpm start -p 8091` → `next start -H ${HOST:-0.0.0.0} -p 8091`, serving a prebuilt `.next`. It does **not** hot-reload; source edits require a rebuild + service restart to appear. — Evidence: `systemctl cat podium-web.service`, `web/frontend/package.json` scripts
- Running `next build` overwrites `.next` in place. While the old `next start` server keeps serving the previous in-memory HTML (old chunk hashes), the on-disk static chunks change, so any asset request in that window returns 400 with `text/html` MIME (browser: "Refused to apply style... MIME type ('text/html')"). The site appears stuck at "Checking session…". — Evidence: live console errors observed; `ls .next/static/css/` hash changed `296af0bbdbe2ffd4.css` → `47857b3ee08e2d46.css`
- Recovery is a service restart: `sudo systemctl restart podium-web.service` loads the new build cleanly. Verified `10.20.20.16:8091/` → 200 and new CSS → 200 `text/css`. The browser still needs a hard refresh to drop stale cached HTML. — Evidence: post-restart curl checks
- `next build` also rewrites `tsconfig.json` (array reformat + adds `<distDir>/types/**/*.ts` to `include`) — machine noise, not a source change. — Evidence: `git diff web/frontend/tsconfig.json` after build

## Decisions

- Prevention approach chosen: **atomic staging swap** (Option A). Build into a staging distDir so the live `.next` is untouched during the slow build, then fast `stop → swap → start`. Zero chunk-mismatch window; ~3s downtime. — Evidence: `web/frontend/deploy.sh`, `web/frontend/next.config.mjs`
- Sidebar made collapsible: top-left `PanelLeft` toggle in the header; open/closed state persisted to `localStorage` key `podium:sidebar-open`. — Evidence: `web/frontend/components/AppShell.tsx`
- Issue card quick-view changed per James: dropped the `PriorityBadge` (low/med/high) and `VerdictPill` (done/review/blocked — the column-duplicate); now shows a colour-coded agent pill (`claude`=orange, `pi`=violet) from `issue.preferred_agent` plus `issue.preferred_model`, falling back to "default agent" when neither is pinned. Age retained. `badges.tsx` exports kept (still used by `RunHistoryList`). — Evidence: `web/frontend/components/IssueCard.tsx`

## Evidence

- `web/frontend/deploy.sh` — atomic deploy: staging build, tsconfig restore, stop/swap/start, verify, rollback note
- `web/frontend/next.config.mjs` — `distDir: process.env.NEXT_DIST_DIR ?? ".next"` (default unchanged)
- `web/frontend/.gitignore` — ignores `.next.staging` / `.next.prev`
- `web/frontend/components/AppShell.tsx` — collapsible sidebar + toggle + localStorage persistence
- `web/frontend/components/IssueCard.tsx` — agent/model quick-view
- `systemctl cat podium-web.service` — `ExecStart=/usr/bin/pnpm start -p 8091`, `Environment=HOST=10.20.20.16`

## Exclusions

- No `/home/james/symphony-host.env` contents.
- No transcript, no secrets.
- All five frontend changes are uncommitted working-tree edits at capture time (latest commit `eef75d1`); deploy script not yet exercised on a real deploy (build-only validation done).

## Open Questions And Follow-Ups

- Commit the five frontend changes (`deploy.sh`, `next.config.mjs`, `.gitignore`, `AppShell.tsx`, `IssueCard.tsx`).
- First real use of `deploy.sh` will exercise the stop/swap/start path end-to-end (build-only validation confirmed the staging distDir override; swap+restart untested live).
- Card shows `preferred_agent`/`preferred_model` (pinned preference), not the last Run's actual agent/model — those live on the `run` table, not the issue-list payload. Showing actual run agent/model would need a new field on the list endpoint.
