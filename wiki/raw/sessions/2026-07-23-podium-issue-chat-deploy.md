# Session Capture: Podium issue-chat spec deploy (#30–#41) — wiki maintenance

- Date: 2026-07-23
- Purpose: correct the prior wiki maintenance diff so it accurately states the full issue-chat implementation status (children #30–#36 and follow-ups #38–#41 closed alongside parent #37; F1 frontend live on `podium-web`).

## Durable Facts

- GitHub Issues **#30–#41 are all CLOSED** as of 2026-07-23. Parent spec #37 closed `2026-07-23T05:30:57Z`. Implementation children: #30 (B1 `comments_md` header stamping) CLOSED; #31 (B2 discussion output contract) CLOSED; #32 (B3 live-tail protocol) CLOSED; #33 (F1 bubble rendering + Variant B + run-row merge) CLOSED; #34 (F2 auto-routing composer + mode pill + conditional Abort) CLOSED; #35 (F3 live-tail consumer + catch-up flow) CLOSED; #36 (F4 creation rework) CLOSED. Acceptance follow-ups: #38 CLOSED `2026-07-23T03:41:52Z`; #39 CLOSED `2026-07-23T03:36:18Z`; #40 CLOSED `2026-07-23T04:33:32Z`; #41 CLOSED `2026-07-23T04:09:19Z`. Evidence: authenticated `gh issue view 30 … 41 --json state,title,closed,closedAt` on the operator-configured `github-personal` SSH-key host alias (no auth material captured here; the alias is recorded in `CLAUDE.md`).
- The F1 slice is the live frontend. `web/frontend/components/IssueChat.tsx` opens with the F1 header comment ("F1 — bubble rendering for the issue chat flyout (#33 / spec §2–4).") and is imported and rendered by `web/frontend/components/IssueFlyout.tsx`; source wiring is on `main`.
- The live `podium-web` service is running the freshly-built bundle. `systemctl is-active podium-web.service` reports `active`; `systemctl status podium-web.service` shows `Active: active (running) since Thu 2026-07-23 13:56:18 UTC`. `web/frontend/.next/BUILD_ID` is `wgN3tmVXMyH-QwuqCFgpP`; the previous bundle is **retained** at `web/frontend/.next.prev/BUILD_ID = vUsX0hEgqsiTSUPbAhhW2` — per `web/frontend/deploy.sh` ("kept at .next.prev for a quick manual rollback"), the previous build is preserved for an optional manual rollback, not actively rolled back.
- The deploy was produced by `web/frontend/deploy.sh` (atomic staging-swap; cache busting; HTTP-200 verification gate). An exact `curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://10.20.20.16:8091/` returns `HTTP 200`. `git status --short` is clean post-deploy (no untracked/staged files).

## Decisions

- Treat the spec's full chain (#30–#36 children, #37 parent, #38–#41 follow-ups) as deployed for wiki purposes. B1 (`comments_md` header stamping) and F1 (bubble rendering + Variant B + run-row merge) are the load-bearing pieces cited here; Slices in adjacent spec areas outside this chain (e.g. Wayfinder tickets #19, #20, #24, #25, #28, #29) are decision/provenance tickets, not open implementation work, and are out of scope for the issue-chat closure note.
- No new claim is admitted. Deployment/closed status is useful page maintenance but not a load-bearing atomic fact (the underlying slice work is already cited at the C-### level on the parent page; nothing new survives a future consolidation that the existing claims wouldn't also survive).

## Evidence

- `wiki/concepts/operator-reply.md` — leading follow-on paragraph was rewritten to record the full #30–#41 closure and live F1 frontend; a separate "Independence note" paragraph carries the precise public-GitHub-gap wording.
- `wiki/index.md` — root Concepts row for `operator-reply.md` now lists the closed #30–#36 chain and #38–#41 follow-ups alongside the live F1 frontend and `BUILD_ID` diff.
- `wiki/CLAIMS.md` — restored from HEAD (`git checkout -- wiki/CLAIMS.md`) after an earlier `gate.py migrate` run in this session accidentally dropped the Notes content from C-0399 and C-0400; rerunning `gate.py migrate` would be redundant since the migration already happened and the original file is canonical.
- `web/frontend/components/IssueChat.tsx` — file header comment confirms F1 ownership (#33 / spec §2–4).
- `web/frontend/components/IssueFlyout.tsx` — `IssueChat` import + usage; the source wiring is on `main`.
- `web/frontend/.next/BUILD_ID` = `wgN3tmVXMyH-QwuqCFgpP` (active) and `web/frontend/.next.prev/BUILD_ID` = `vUsX0hEgqsiTSUPbAhhW2` (previous, retained for manual rollback per `deploy.sh`).
- `systemctl status podium-web.service` (`active (running)`), `curl http://10.20.20.16:8091/` (`HTTP 200`), `git status --short` (clean).
- `gh issue view 30 … 41 --json state,title,closed,closedAt` — twelve CLOSED responses with timestamps.

## Exclusions

- No secrets, credentials, auth tokens, `symphony-host.env` contents, full session transcript, or raw pasted user content were captured. Only the public issue `state`/`title`/`closed`/`closedAt` fields were read; the `gh` SSH host alias `github-personal` is operator-configured and recorded in `CLAUDE.md`, not captured here.
- Public GitHub issue verification via unauthenticated web was not available; authenticated `gh` and the local build/source evidence are the grounds for the status update. The HTTP-200 active-unit and source-wiring checks are unaffected by the public-issue probe gap.

## Open Questions And Follow-Ups

- None for the issue-chat closure note; the spec's #30–#41 chain is closed and the F1 frontend is live. Any follow-up work (e.g. future Variation of F2/F3/F4 behaviour, regressions in B1 stamping) would be its own ticket.
- `podium-api.service` model-validation restart lessons (C-0311/C-0315/C-0388) remain applicable if a future slice changes API-side rendering; the current bubble-rendering change is a frontend-only deploy via `deploy.sh`, so no API restart is implied here.
