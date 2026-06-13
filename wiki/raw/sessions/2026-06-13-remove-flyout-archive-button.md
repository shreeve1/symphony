# Session Capture: Remove the IssueFlyout archive button

- Date: 2026-06-13
- Purpose: James asked to remove the dedicated "Archive" button from the issue flyout. Archiving remains available through the existing state chip.
- Scope: Frontend UI affordance removal + e2e test adaptation. No API, schema, or engine change.

## Durable Facts

- The dedicated "Archive" button in `IssueFlyout` (rendered between `MetadataChips` and the tab strip, `data-testid="archive-issue"`, no-confirm `onPatch({ state: "archived" })`) was removed. — Evidence: `web/frontend/components/IssueFlyout.tsx` (block formerly at ~lines 656-665, deleted)
- Archiving an issue is now done only through the flyout **state chip** (`edit-state` select). `archived` is a member of `STATE_KEYS` (derived from `STATES` in `web/frontend/lib/issues.ts:11`), so the state dropdown already offers it as an option. — Evidence: `web/frontend/components/IssueFlyout.tsx:237,253-258`, `web/frontend/lib/issues.ts:11`
- The state chip remains the restore path too (archived → todo), unchanged. — Evidence: `web/frontend/tests/archive.spec.ts` "state chip restores archived issue"

## Decisions

- Remove the redundant flyout Archive button; rely on the state chip for both archive and restore. — Evidence: James request this session; `web/frontend/components/IssueFlyout.tsx`
- The now-obsolete e2e test "archive button hidden on already archived issue" was deleted (the button no longer exists for any state). The "archive button moves issue to archived column" test was retargeted to drive the state chip and renamed "state chip moves issue to archived column". — Evidence: `web/frontend/tests/archive.spec.ts`

## Evidence

- `web/frontend/components/IssueFlyout.tsx` — button block removed; `MetadataChips` now sits directly above the tab `<div>`.
- `web/frontend/tests/archive.spec.ts` — two tests changed (one retargeted to `edit-state`, one deleted); column-collapse and state-chip-restore tests untouched.
- `web/frontend/lib/issues.ts:11` — `{ key: "archived", ... }` confirms the state chip offers archived.

## Exclusions

- No secrets. No engine/API/schema change. Retention purge (#036), engine-terminal contract (#035), and board column collapse (#033/#034) are unaffected.

## Open Questions And Follow-Ups

- Change is in the working tree only — not committed, not deployed. `podium-web` serves the prior build until a frontend rebuild + `deploy.sh` staging swap.
- Card-hover archive affordance was already deferred; removing the button does not change that.
