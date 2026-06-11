---
id: 020
title: Engine dispatch end-to-end against Podium — trading cutover
status: in-progress
blocked_by: [016, 019]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Flip the `trading` binding to `tracker: podium`. From this point a real
operator-filed issue in Podium triggers a real `pi` dispatch, the Run row
gets the verdict, the log lands on disk under `runs/{id}.log`, and the
issue transitions to In Review in Podium.

Steps:

1. Update `bindings.yml` for `trading`: add `tracker: podium`. Plane
   tracker contract block stays (commented out) for rollback. Operator
   confirmation required at the moment of edit (live infra).
2. The dispatch path in `scheduler.py` reads/writes through the adapter
   selected at startup (already wired in S019). No further engine code
   changes expected — if changes ARE required, document them in the
   slice's implementation notes.
3. Run rows are populated end-to-end:
   - `state` flows queued → running → completed.
   - `verdict`, `summary`, `cost_usd`, `input_tokens`, `output_tokens`
     scraped from pi stdout markers.
   - `log_path` set to absolute `runs/{id}.log`.
   - `started_at` / `ended_at` populated.
4. The completion comment (concise summary for operator) lands in
   `issue.comments_md` as an appended block; the full output lands in
   `issue.context_md`.
5. The `trading` Plane project remains untouched (read-only fallback for
   rollback). Do not archive Plane in this slice — that is S023.

## Acceptance criteria

- [ ] `bindings.yml` for `trading` declares `tracker: podium`.
- [ ] Smoke ticket filed via Podium UI (S014) results in a Run row reaching `completed` state with non-null verdict within `run_timeout_ms`.
- [ ] `runs/<id>.log` exists on disk, contains stdout + stderr.
- [ ] `comments_md` for the smoke issue contains a Run summary block; `context_md` contains the detailed output block.
- [ ] `uv run pytest` passes (no regressions on existing Plane-binding tests).
- [ ] `tests/test_trading_podium_dispatch.py` mocks `pi` and asserts the full happy-path lifecycle without touching the real Plane API.
- [ ] Rollback documented in `web/README.md`: operator removes `tracker: podium` and `systemctl restart symphony-host.service` reverts to Plane for trading.
- [ ] No writes to the trading Plane project after cutover (verified by capturing `plane_adapter` calls in a test against the cutover binding).

## Verification

```
cd /home/james/symphony && uv run pytest
```

Manual smoke after cutover (operator-driven, not Ralph-automated):

```
# file a low-risk ticket via Podium, watch for completion
journalctl -u symphony-host.service -f | grep 'binding=trading'
```

## Blocked by

- #016 (Run detail UI needed to inspect dispatched runs)
- #019 (Tracker Adapter must exist before binding can use it)

## Notes

- Live infra: requires `systemctl restart symphony-host.service`. James
  must approve at the moment of action per `CLAUDE.md`.
- `trading` is the disposable proof-of-concept binding. Homelab cutover is
  a separate, later operator decision — not part of this slice.
- `issue.preferred_agent` / `preferred_model` are free text — no enum or FK
  validation at create or patch (#014 review). Dispatch must handle unknown
  values gracefully (fall back to the binding's `default_agent` / configured
  model) rather than assume they are valid.
