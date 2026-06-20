# Session Capture: ADR-0015 Wave C — patrol→Podium cutover (auth gap fixed, dry-run passed, cutover deferred)

- Date: 2026-06-20
- Purpose: Execute plan 59 Wave C (route Temporal patrols to Podium). Surfaced a blocking auth-model mismatch, resolved it (operator chose service-token auth on podium-api), built the worker wiring, dry-ran the live adapter path, paused before the worker restart per operator.
- Scope: Symphony auth change + 2nd gated podium-api window + homelab Wave C wiring + live dry-run. Worker env edit + patrol-worker restart intentionally deferred.

## Durable Facts

- **podium-api auth was cookie-only; Wave A's Podium transport assumed Bearer.** The `require_auth` middleware (`web/api/main.py`) accepts ONLY a password→session cookie (`/api/health` + `/api/auth/*` exempt); it never inspected `Authorization`. Wave A's `PodiumHttpTransport` (homelab) sends only `Authorization: Bearer …`, and its docstring's claim that "the patrol binding's create endpoint runs unauthenticated today" was FALSE. As-built, the patrol cutover would 401 on every Podium write. — Evidence: `web/api/main.py:329-340` (middleware), `web/api/auth.py` (no bearer path), `automation/homelab-stack/src/homelab_router/podium_http.py:36-39`.
- **Operator decision (2026-06-20): add a Bearer service-token path to podium-api** (Option B; the other options were cookie-login-in-transport (homelab-only) or wire-but-stay-on-Plane). This reopens the excluded service. — Evidence: this session (AskUserQuestion).
- **Implemented + committed (symphony `69bf3f3`):** optional `PODIUM_API_TOKEN`. `AuthConfig` gained `api_token`; `config_from_environment` reads `PODIUM_API_TOKEN` (unset → cookie-only, backward compatible); new `verify_bearer_token` does a constant-time (`hmac.compare_digest`) match on `Authorization: Bearer <token>`; the middleware accepts it as a fallback to the cookie. Tests added in `web/api/tests/test_auth.py` (good token→200, bad→401, unset→401). — Evidence: `web/api/auth.py`, `web/api/main.py`, commit `69bf3f3`.
- **2nd gated podium-api window APPLIED (2026-06-20):** generated a 256-bit token, appended `PODIUM_API_TOKEN=…` to `/home/james/symphony-host.env` (perms `600` preserved, value never printed), restarted `podium-api.service`. Verified live: no-auth→401, bad-bearer→401, **good-bearer→200**, cookie→200 (backward compatible). — Evidence: `journalctl -u podium-api.service`; live HTTP probes.
- **Wave C wiring built + committed (homelab `d160955`).** `WorkerConfig` gained `patrol_tracker` (default `podium`), `podium_base_url` (default `http://127.0.0.1:8090`, loopback — worker is same host as podium-api), `podium_api_token` (secret, redacted in repr), `patrol_binding` (default `homelab`, per C-0267). `from_env` requires `PODIUM_API_TOKEN` when tracker is podium (fail-at-startup, not first-write). `worker.py` selects `PodiumAdapter(binding=homelab, PodiumHttpTransport(...))` for podium else `PlaneAdapter`; activity names unchanged (no Temporal signature change); podium transport closed in `finally`. Existing env-split tests updated with `PATROL_TRACKER=plane`. — Evidence: `automation/homelab-stack/src/homelab_router/config.py`, `.../homelab_worker/worker.py`, commit `d160955`.
- **Live dry-run PASSED 10/10 and caught a real integration bug.** `PodiumAdapter.find_by_external_id` did `result.get("results", [])`, but the live `GET /api/bindings/{name}/issues?external_id=` returns a **bare JSON list** — Wave A only tested against the in-memory mock (which wraps rows in `{"results": […]}`), so dedup would crash with `AttributeError` in production. Fixed to accept both shapes + bare-list regression test (homelab `2e4fad6`). Re-run: create→archive→dedup→re-upsert(no dup)→reopen→teardown all PASS; the `<!-- patrol-status -->` marker round-trips in Podium markdown (live confirmation of C-0265's marker-survival claim); test issue id=62 created then DB-deleted; **no agent dispatch** triggered. — Evidence: dry-run output; `automation/homelab-stack/src/homelab_router/podium_adapter.py`, commit `2e4fad6`.
- **Dispatch-eligibility fact:** a plain `todo` Podium issue in any binding (incl. infra `homelab`) is dispatch-eligible via `adapter.list_candidates()`/`_reserve_candidate` (`scheduler/__init__.py:1201-1230`) — infra scheduled-selection needs the `SCHEDULED` *label* which Podium lacks, but the normal-candidate fallthrough still applies. So a lingering test `todo` could be claimed within ~30s; the dry-run archives sub-second to avoid this. — Evidence: `scheduler/__init__.py:1126-1230,2585-2624`.

## Decisions

- Resolve the auth gap via a podium-api service token (excluded-service change), not transport cookie-login. — operator.
- **Worker cutover (env edit + `homelab-temporal-patrol-worker.service` restart) DEFERRED** — operator chose "dry-run only, then pause". Patrols still run on Plane until the worker is reconfigured + restarted.

## Evidence

- Commits: symphony `69bf3f3` (bearer auth); homelab `d160955` (Wave C wiring), `2e4fad6` (adapter list-shape fix).
- `/home/james/symphony-host.env` — now carries `PODIUM_API_TOKEN` (perms 600).

## Exclusions

- `PODIUM_API_TOKEN` value, the password hash/session secret, and `symphony-host.env` contents never printed.
- **Working-tree alert (unrelated, surfaced to operator):** during this session a concurrent process deleted the entire `.claude/` directory (14 symphony skills, hooks, settings, WORKFLOW templates) and stripped ~142 lines from `CLAUDE.md` in `/home/james/symphony`; all recoverable from git HEAD. Left untouched. Caused 15 `tests/skills/` `FileNotFoundError`s in the full suite — environmental, not from this work.

## Open Questions And Follow-Ups

- **Finish Wave C cutover when operator says go:** append `PODIUM_API_TOKEN` + `PATROL_TRACKER=podium` to `/etc/homelab-stack/temporal-worker.env` (sudo); restart `homelab-temporal-patrol-worker.service`; confirm `patrol_tracker=podium binding=homelab` log line; observe a real patrol cycle writing to the `homelab` Podium binding.
- Decide on the `.claude/`+`CLAUDE.md` deletion (restore vs intentional reorg).
- Optional symphony nit (from window #1): `INITIAL_REVISION` still 0008 → per-startup `podium_schema_revision_mismatch` warning.
