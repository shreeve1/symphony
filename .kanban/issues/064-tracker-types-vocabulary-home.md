---
id: 064
title: tracker_types.py — single home for tracker vocabulary
status: pending
blocked_by: [63]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Phase 3 of the review (findings L3-03, L3-01, L3-02, L3-05, L1-06 in `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). The tracker-agnostic engine vocabulary currently lives inside the Plane-specific module and is duplicated into the Podium adapter. Establish the layering `tracker_contract → tracker_types → tracker_adapter → {plane_adapter, tracker_podium}`.

- **L3-03** — create neutral, zero-in-scope-dependency `tracker_types.py` holding `CandidateIssue`, `CommentPayload`, `IssuePayload` plus the shared parse helpers (`_extract_labels`, `_is_state`, `_candidate_from_issue`, `_next_cursor`, `_page_items`). `plane_adapter` and `tracker_podium` import from it.
- **L3-01** — define `CandidateIssue` once in `tracker_types`; delete the field-equivalent duplicate in `tracker_podium.py:42-73` and the original in `plane_adapter.py:53-82`.
- **L3-02** — make `tracker_adapter.py` the single `TrackerAdapter` Protocol home; reconcile the method set as the union (`list_issues`, `post_comment`, `get_run`, `record_run`, plus the optional context/run methods); import data types from `tracker_types`; delete `plane_adapter.py:136-179`'s copy; repoint `scheduler.py:34`.
- **L3-05 + L1-06** — consolidate `_extract_labels` / ISO-parse / `_next_cursor` (triplicated across `plane_adapter`, `scheduler`, `blocked_reconciler`) into `tracker_types`; call-site differences (label_ids source, epoch+idx fallback ordering) become arguments. Reconcile the two ISO variants into one with an optional fallback knob.

Repoint all importers, including `web/api/main.py:927` (`from tracker_podium import CandidateIssue` → `tracker_types`) and the `plane_poller` re-export.

## Acceptance criteria

- [ ] `tracker_types.py` exists with no in-scope/`web.*` import deps; defines `CandidateIssue`/`CommentPayload`/`IssuePayload` and the shared parse helpers once.
- [ ] No `CandidateIssue` definition remains in `plane_adapter.py` or `tracker_podium.py`; both import it from `tracker_types`.
- [ ] `TrackerAdapter` Protocol exists only in `tracker_adapter.py` (union method set); `plane_adapter.py` has no Protocol copy; `scheduler.py:34` imports it from `tracker_adapter`.
- [ ] `web/api/main.py` imports `CandidateIssue` from `tracker_types`, not `tracker_podium`.
- [ ] `_extract_labels` / ISO parse / cursor helpers exist once in `tracker_types`; `scheduler.py` and `blocked_reconciler.py` import them; the ISO fallback difference is a parameter.
- [ ] Import graph stays acyclic (no cycle introduced).
- [ ] `uv run pytest` passes (web/api import-repoint tests included).

## Verification

`uv run pytest`

## Blocked by

- Blocked by #063 (serializes the `scheduler.py` edit ordering).
