# Plan — #127: auto-generate Issue titles from the description

**For:** an implementation session (the grill that produced this is complete).
**Date created:** 2026-06-24.
**Operator goal (verbatim intent):** "Is there a way that we can have Symphony
auto-generate titles from the description? If this is possible, we would remove
the title, option, input field, and requirement from a new issue creation."

> This document is the resolved design from a `/grill-me` session. All four
> design forks below were settled with the operator. It is a plan, not yet an
> implementation.

---

## Decision summary (operator-confirmed)

| # | Decision | Choice |
|---|----------|--------|
| 1 | **Generation locus** | **(A) Synchronous at create-time** — title produced during `POST /api/issues`, before the row is returned. |
| 2 | **Failure behaviour** | **(A2) Deterministic fallback** — on any pi failure/timeout/empty output, derive the title from the description rather than failing the create. |
| 3a | **Description requiredness** | **Required** — with the title field gone, the description is the sole title source, so `description` flips from optional to `min_length=1`. |
| 3b | **Generation owner** | **(i) Server-side** — the API owns title synthesis; `title` is removed from the request body entirely. |
| 4 | **Model** | Reuse the existing configured one-shot pi (`pi_provider`/`pi_model`); no new env var. |

---

## Grounded facts (verified this session)

- **The Podium web API has no LLM client today.** Its only path to a model is
  shelling out to `pi`. The one-shot dispatch shape already exists in
  `agent_runner.py:120` (`_build_pi_command`): `pi --print --no-session
  --provider <p> --model <m> "<prompt>"`, returning the title on stdout.
- **The API process already has what it needs:** `config.py` carries `pi_bin`,
  `pi_provider` (default `"zai"`), and `pi_model` (default `"glm-5.1:high"`);
  `web/api/main.py` already imports `subprocess` and resolves per-binding
  `repo_path`. No new config or plumbing is required to reach a model.
- **Title is non-nullable today.** `IssueCreate.title: str = Field(min_length=1)`
  (`web/api/main.py:561`); `title` is in `NON_NULLABLE_FIELDS`
  (`web/api/main.py:634`). Description is currently optional
  (`description: str | None = None`).
- **Title is consumed in three places** — none of which feed the agent prompt,
  so the *value* is purely human-facing:
  - board card render: `web/frontend/components/IssueCard.tsx:136`
  - flyout header: `web/frontend/components/IssueFlyout.tsx:1122`
  - blocked-reconciler pass-comment matching: `blocked_reconciler.py:259`
- **There are two issue-creation paths; only one is in scope.**
  - `POST /api/issues` via `IssueCreate` — the New Issue modal. **In scope.**
  - `web/cli/podium_issues.py:_insert_issue` — plan-slice issues, direct INSERT
    that bypasses `IssueCreate` and already supplies `slice_.title`.
    **Out of scope, untouched.**
- **Frontend create form:** `web/frontend/components/NewIssueModal.tsx` — the
  `title` state + input + `disabled={!title.trim()}` submit guard, and
  `web/frontend/lib/api.ts` `IssueCreate` interface (`title: string`,
  `description?: string`).

---

## Assumed defaults for the low-stakes details

These were not grilled (reversible, obvious default); flagged here so the
implementer can adjust:

- **Prompt:** fixed instruction — "Generate a concise issue title (≤80 chars,
  no surrounding quotes, no trailing punctuation) summarising this issue
  description" — with the description as the content. Strip wrapping quotes /
  whitespace from the model output before storing.
- **A2 fallback rule:** first non-blank line of the description, trimmed to
  ≤80 chars on a word boundary. Used on pi non-zero exit, timeout, or
  empty/whitespace stdout.
- **Timeout:** 15s on the pi subprocess so a hung provider can't wedge the
  create request.
- **Injection seam:** title generation lives in a small helper with an
  injectable runner (mirror the `run_func` parameter pattern in
  `verify_pi_support`, `agent_runner.py`) so tests stub pi and no test depends
  on a live binary.

---

## Implementation plan

1. **Title-gen helper (new).**
   - Add a function (e.g. `generate_issue_title(description, *, run_func=subprocess.run)`)
     that builds the one-shot pi command from configured `pi_bin`/`pi_provider`/
     `pi_model`, runs it with a 15s timeout, strips/validates output, and
     returns the title — or the A2 fallback on any failure/timeout/empty.
   - Location: alongside the API create handler (or a small module imported by
     it). Keep it injectable for tests.
   - **Verify:** unit tests — happy path (stubbed pi returns a title),
     fallback on non-zero exit, fallback on timeout, fallback on empty stdout,
     ≤80-char + quote-stripping normalisation.

2. **`IssueCreate` contract change (`web/api/main.py`).**
   - Remove `title` from `IssueCreate`.
   - Change `description` to required: `description: str = Field(min_length=1)`.
   - In the create handler, call the helper with the description and write the
     returned title into the existing INSERT (`web/api/main.py:995`).
   - Remove `"title"` from `NON_NULLABLE_FIELDS` *only if* it is no longer
     reachable as an operator-settable create field — confirm PATCH still
     allows title edits (operators must be able to rename); if PATCH keeps
     title, leave the PATCH-side guard intact.
   - **Verify:** `web/api/tests/test_issue_create.py` — create with description
     only yields a generated title; create with no/empty description is 422;
     `title` in the body is rejected as `extra_forbidden` (400). Run the API
     test suite.

3. **Frontend modal (`web/frontend/components/NewIssueModal.tsx`).**
   - Remove the `title` state, the Title `<input>`, and the
     `!title.trim()` submit-disable guard (gate on `description.trim()`
     instead). Stop sending `title`; send `description` unconditionally.
   - Update the optimistic-create temp card: it currently sets
     `title: body.title`. Replace with a placeholder (e.g. first line of the
     description or "Generating title…") since the real title now arrives only
     in the server response; the `onSuccess` swap already replaces the temp row
     with the canonical server row.
   - **Verify:** `web/frontend/tests/new-issue.spec.ts` updated — submit with
     description only; assert the created card shows the server title.

4. **Frontend types (`web/frontend/lib/api.ts`).**
   - `IssueCreate`: drop `title`, make `description` required.
   - **Verify:** typecheck / frontend build passes.

5. **Wiki + CONTEXT.** This sets a new create-path contract (a durable
   architecture change → wiki trigger). Update
   `wiki/concepts/podium-tracker.md` (the create-contract section), add a claim
   to `wiki/CLAIMS.md`, and run a `/wiki-update` pass. No CONTEXT.md glossary
   term changes (no new domain vocabulary).

---

## Risks / watch-items for the implementer

- **API now shells out to pi on the hot create path.** First time the web tier
  depends on a model. The injectable seam + A2 fallback keep tests hermetic and
  keep create resilient to provider outages, but the latency budget (≤15s) is
  real — confirm acceptable UX (optimistic card already hides most of it).
- **PATCH title-edit must survive.** Removing title from *create* must not
  remove an operator's ability to rename later. Confirm the PATCH path and its
  `NON_NULLABLE_FIELDS` guard are untouched.
- **`external_id` dedup create path** (`POST /api/issues`, ADR-0015) shares the
  same handler — adapters that create via this endpoint now also get
  auto-titled and must supply a description. Confirm no adapter relied on
  passing a title without a description.
- **Plan-slice CLI path is intentionally excluded.** If a future requirement
  wants those auto-titled too, that's a separate change to
  `web/cli/podium_issues.py`.

---

## Verification (whole change)

- `web/api` test suite green (esp. `test_issue_create.py`, `test_issue_patch.py`).
- Frontend typecheck + `new-issue.spec.ts` green.
- Manual: create an issue in the modal with only a description → a sensible
  title appears on the board card; simulate pi failure → A2 fallback title
  appears, create still succeeds.
