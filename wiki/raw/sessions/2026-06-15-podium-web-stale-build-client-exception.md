# Session Capture: Podium web "client-side exception" from stale build under live next start

- Date: 2026-06-15
- Purpose: Diagnose a browser "Application error: a client-side exception has occurred" on the Podium frontend; root-caused to a known deploy hazard (C-0110) recurring because a bare `next build` ran against the live `next start`.
- Scope: Captures the recurrence, the new symptom string, the chunk-404 mechanism observed, and the restart-alone remedy. Does not re-derive the full deploy.sh fix (already in C-0110 / `analyses/podium-frontend-deploy-cosmetics.md`).

## Durable Facts

- Symptom presented to the operator: browser shows `Application error: a client-side exception has occurred (see the browser console for more information)` — a Next.js client-side render/hydration failure, distinct from the previously-recorded "Checking session…" hang. Evidence: operator report this session.
- `podium-web.service` MainPID 504346 booted `Sun 2026-06-14 23:43:01 UTC` (`next start` loads the `.next` build manifest into memory at boot and does not reload it). `.next` on disk was rebuilt `2026-06-15 02:24` (`.next/BUILD_ID`, `.next/build-manifest.json` mtimes) — ~3h after server boot. Evidence: `systemctl show podium-web.service --property=MainPID,ExecMainStartTimestamp`, `stat -c '%y' .next/BUILD_ID .next/build-manifest.json`.
- The running server served HTML referencing the **old** app-router chunk hashes `app/[binding]/page-d526ae8fbf56201a.js` and `app/layout-124a785f4f59aa0c.js`; those files no longer exist on disk (rebuild renamed them to `page-ece4deabd0316775.js` and `layout-e593ac5b904adb07.js`). Requesting the old URLs returned **400**. The 404/400 on the page+layout chunks is what breaks hydration → client-side exception. Evidence: `curl http://10.20.20.16:8091/homelab` HTML grep + per-chunk `curl -w '%{http_code}'`; `ls .next/static/chunks/app/`.
- Trigger this time was a **bare `next build` run against the live `web/frontend` dir** (not `deploy.sh`), reproducing the C-0110 in-place-rebuild hazard. `deploy.sh` (staging distDir + atomic swap) was bypassed.
- Remedy applied: `sudo systemctl restart podium-web.service` (James-approved). New MainPID 1007208, `ActiveEnterTimestamp Mon 2026-06-15 05:28:16 UTC`. After restart, served HTML referenced the current hashes and all 11 chunks (incl. `app/[binding]/page-ece4deabd0316775.js`, `app/layout-e593ac5b904adb07.js`) returned **200**; `/homelab` returned 200. Restart-alone worked because a **valid production `.next` already existed on disk** (the 02:24 build completed cleanly) — only the in-memory manifest was stale. Evidence: post-restart `curl` chunk checks this session.
- The 02:24 build folded in the then-uncommitted file-browser feature (`web/frontend/components/FileBrowser.tsx`, `FileEditor.tsx`, `lib/monaco.ts`, `app/[binding]/files/`), which the restart made live. Flagged to operator.

## Decisions

- Restart `podium-web.service` rather than rebuild — the on-disk build was already valid; James approved the restart. Evidence: this session.

## Evidence

- `systemctl show podium-web.service --property=MainPID,ExecMainStartTimestamp,ActiveEnterTimestamp` — boot vs build timing, restart confirmation.
- `stat -c '%y' .next/BUILD_ID .next/build-manifest.json` — build mtime (02:24) vs server boot (23:43).
- `curl http://10.20.20.16:8091/homelab` + per-chunk `curl -o /dev/null -w '%{http_code}'` — 400 before restart on old `app/[binding]/page-*` / `app/layout-*` chunks, 200 after.
- `ls .next/static/chunks/app/` — current on-disk hashes differ from served HTML.

## Exclusions

- No secrets or `/home/james/symphony-host.env` values read or written.
- Did not commit the uncommitted file-browser feature; did not run `deploy.sh` or rebuild (restart sufficed).

## Open Questions And Follow-Ups

- Recurrence shows `deploy.sh` is not consistently used for frontend rebuilds. Consider a guard/wrapper so a bare `next build` against `web/frontend` cannot happen, or document "never `next build` the live dir — always `deploy.sh`" more prominently.
- The file-browser feature (`FileBrowser`/`FileEditor`/Monaco/`/[binding]/files`) is now live via the restart but remains uncommitted; confirm it is intended to be live and commit or stash accordingly.
