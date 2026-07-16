# Handoff — issue #389 file buttons: continue work

## Why this exists

The Maximize/Restore toggle on the file-view page is in place but the operator
flagged that the two buttons were in different places. The session that
handled #389 unified them into one bottom-right control (commit `d304da3`),
but the broader question of "the file buttons" — top-right Save, top-left
binding-name header, bottom-right Maximize/Restore, plus the Save button's
read-only treatment and the editor's overall chrome — hasn't been reviewed
end-to-end. A fresh session should pick this up.

## What's done on issue #389 (do NOT redo)

Two commits on local `main`:

1. `4672f1d` — initial Maximize/Restore, mirroring IssueFlyout
   `toggleMaximized`. Localstorage key `podium-files-expanded` (separate from
   `podium-flyout-maximized`). Tree pane hidden via `hidden` class but kept
   mounted. Placement was split between tree-pane header (Maximize) and
   bottom-right (Restore).
2. `d304da3` — placement follow-up. Dropped the in-tree button; ONE control
   sits in the bottom-right of the page in both states. Label flips Maximize
   ↔ Restore; aria-pressed tracks the boolean. Single testid
   `files-expand-toggle`. Net `-14` LOC vs the prior split.

Verified at the time:
- `tsc --noEmit` (from `web/frontend`) — clean.
- `playwright test files.spec.ts --reporter=list` — 2/2 pass (~18.6s).
- `./deploy.sh` — atomic rebuild + `podium-web` swap; `is-active` +
  `curl /homelab/files` = HTTP 200.
- `podium-api` and `symphony-host` NOT touched (no API or scheduler code
  changed).

## State of the service trio

| service               | PID        | started              | needs restart?             |
|-----------------------|------------|----------------------|----------------------------|
| `podium-web.service`  | (see systemctl show) | 2026-07-15 ~18:51 UTC | No — already running d304da3 |
| `podium-api.service`  | (see systemctl show) | 2026-07-15 ~13:54 UTC | Only if a code change lands under `web/api/` |
| `symphony-host.service` | (see systemctl show) | 2026-07-14 ~05:05 UTC | Only if a code change lands in the scheduler |

Files route is `200`.

## Where the next session should look

### Files relevant to "the file buttons"

- `web/frontend/app/[binding]/files/page.tsx` — current source of truth for
  the layout (tree pane + editor + the unified bottom-right Maximize).
- `web/frontend/components/FileBrowser.tsx` — file-row presentation, copy-path
  button, expand/collapse chevrons.
- `web/frontend/components/FileEditor.tsx` — file-editor chrome: top header
  with the file path (`path` string) on the left and **Save** on the right;
  read-only badge; Monaco editor area; the empty-state
  ("Select a file") has no header at all.
- `web/frontend/tests/files.spec.ts` — round-trip test for the toggle;
  treats Save's interaction with the toggle as the regression test surface.
- `web/api/files/...` — backend handlers behind the `/api/bindings/<binding>/files`
  read + PUT APIs (no UI change).

### Operator-noticed UX surface

When the operator was concerned about "the maximize and restore button
[not] in the same place," they surfaced an implicit review of the overall
file-button layout. The current chrome is:

- **Top-left** of the page: binding-name h2 (`{binding}`).
- **Top-right** of the editor (loaded state only): `<button data-testid="file-save">Save</button>`.
- **Top-right** of the editor (empty state): nothing — `<div data-testid="file-editor-empty">Select a file</div>` is centered.
- **Bottom-right** of the page (always): Maximize/Restore `<button data-testid="files-expand-toggle">`.
- **Per file row**: hover-revealed copy-path button (`data-testid="file-row-copy"`).

Things the next session might want to consider (skim, don't pre-decide):

1. Is the Save button placement in the editor header intentional, or should
   it move to the page-level chrome so the operator can reach it when the
   editor's empty state is showing? (Right now if you open a file, then
   open another file in the tree, the Save button position stays consistent
   but only within loaded editor renders.)
2. Should the binding-name header (top-left) be augmented with a binding
   selector (like a workspace switcher)? There is no wiki precedent for
   this on Podium; current Podium binding navigation is by URL only.
3. The empty state hides everything except "Select a file." If users
   arrive at `/<binding>/files` without an intuitive next step, adding
   a hint or a most-recently-edited file list would help — but this is
   new feature work, not "the file buttons" follow-up.
4. The toggle uses `Maximize ↔ Restore` labels. Some apps prefer
   `Expand ↔ Collapse`, `Hide tree ↔ Show tree`, or icon-only (⤢/⤡). If the
   operator has an opinion, it's a one-liner change to either label.
5. Keyboard shortcut? (IssueFlyout doesn't have one either, so default to
   consistency rather than add new keybindings.) Probably leave alone.

## The read-only state gap (worth noting)

`FileEditor.tsx:120–127` shows a read-only badge when the file's `editable`
flag is false. The Save button is also disabled. There is no toggle or
"View raw" affordance — read-only is shown only by the badge. If the
operator wants read-only files to also show a small icon-button hint, that's
trivial; otherwise leave alone.

## Where the next handoff (e2e troubleshooting) lives

A separate handoff already exists at
`/home/james/symphony/handoffs/2026-07-15-issue-389-e2e-troubleshooting.md`
covering the **24-unrelated-Playwright-failures** cluster — read THAT doc
if the operator's question is about test flakiness, not UI placement.

## Suggested skills for the next session

- **`grill-me`** — if the operator wants to keep iterating on the layout and
  there are real design choices (where should Save live; icon vs label;
  shortcut key); *do not* use it for routine tweaks the operator already
  named.
- **`dev-test`** — when a code change lands, write the matching Playwright
  test extension first, then implement.
- **`diagnose`** — *not* the right tool here; nothing to investigate. The
  e2e failures are a separate issue with their own handoff.
- **NOT `autoagent`** — no hill-climb here.
- **NOT `ponytail-review`** — nothing to delete.

## Command cheatsheet

```bash
# Run from /home/james/symphony/web/frontend; cwd matters.
cd /home/james/symphony/web/frontend
./node_modules/.bin/tsc --noEmit
/home/james/symphony/web/frontend/node_modules/.bin/playwright test files.spec.ts \
  --reporter=list

# Deploy (atomic):
./deploy.sh

# Service state:
systemctl is-active podium-web.service
systemctl is-active podium-api.service
systemctl is-active symphony-host.service

# Page check (smoke):
curl -sS -o /dev/null -w "files=%{http_code}\n" \
  "http://10.20.20.16:8091/homelab/files"
```

**DO NOT use `pnpm exec playwright …`** — corepack triggers an `install`
side-effect that errors when cwd is the repo root (no package.json there).
Use the absolute path or run from `web/frontend`.

## Open questions for the operator (only if needed)

- Is the layout **done done**, or is there another spot/label/shortcut
  change they want?
- Should the next session also pick up the unrelated e2e failure cluster
  (24 tests failing on `main` baseline), or keep these scopes separate?
- Is there a maintained design system / icon library the operator wants
  used for the toggle? (Current code uses plain text labels, no icons.)
