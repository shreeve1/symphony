---
title: Blocked reconciler implementation
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - blocked_reconciler.py
  - wiki/raw/runbook-symphony.md
confidence: high
tags: [blocked-reconciler, patrol, regex, decision, plane-adapter, page-limit]
---

# Blocked reconciler implementation

`blocked_reconciler.py` (502 LOC) sweeps the Plane Blocked column, evaluates each issue against an ordered rule list, and (when `apply=true`) transitions cured tickets to their target state with an explanatory Plane comment. The runbook covers operational intent; this page documents the implementation contract.

## Why it exists

Symphony's main scheduler operates on Todo only. Patrol issues that hit a transient failure (e.g. `qbittorrent-ct108: SSH probe failed`) get parked in Blocked; the patrol may post a follow-up *pass* on the next cycle without anything moving the issue out. Result: a steadily-growing Blocked column full of already-cured tickets. AUTO-100/101/103/110 (Apr-May 2026) are the cited evidence [source: blocked_reconciler.py#1-15].

## Pagination caps

```
BLOCKED_PAGE_SIZE                = 50
MAX_BLOCKED_PAGES_PER_TICK       = 3
MAX_COMMENT_PAGES_PER_ISSUE      = 3
```

Conservative caps to match `plane_poller.MAX_PAGES_PER_TICK`. "A growing Blocked column is itself a signal worth surfacing in logs, not something to silently chew through" [source: blocked_reconciler.py#45-50].

## Comment classification regexes

```
_PATROL_PASS_RE          = r"Patrol pass for\s+(?P<target>[^\s:]+)[^\n]*"  (case-insensitive)
_PATROL_FAIL_RE          = r"Patrol fail for\s+(?P<target>[^\s:]+)|SSH probe failed|probe failed"  (case-insensitive)
_CONSECUTIVE_PASSES_RE   = r"consecutive_passes\s*=\s*(?P<n>\d+)"  (case-insensitive; diagnostic only)
_SYMPHONY_COMPLETED_RE   = r"Symphony completed:"  (case-insensitive; weaker signal — agent touched ticket post-block)
```

[source: blocked_reconciler.py#56-69]

Comment body matched against both `comment_html` and `comment_stripped` so the reconciler is resilient to whichever form the adapter returns [source: blocked_reconciler.py#52-54].

## `ReconcileRule` data shape

Fields [source: blocked_reconciler.py#73-109]:

| field | purpose |
|---|---|
| `name` | short identifier in logs and reconciler comments |
| `external_id_prefix` | only match issues whose `external_id` starts with this; empty string matches everything (use sparingly) |
| `target_state` | `PlaneState` or `TrackerRole` to move issue to when rule fires |
| `min_pass_comments_since_fail` | require this many **distinct** patrol-pass comments since the most recent failure (or since ticket creation). Default `1` ("any pass since last fail"); patrol rule uses `2` so a one-off transient pass does not auto-resolve |
| `require_symphony_completion` | when true, require `Symphony completed:` comment newer than most recent failure |
| `comment_template` | optional override; `{target_state}` and `{rule}` interpolated |

**Why distinct comments, not `consecutive_passes=N`**: the homelab patrol worker upserts a fresh ticket per cycle, resetting the counter to 1 on every run; real AUTO-110 evidence shows every pass comment carries `consecutive_passes=1`. Counting distinct passes is the only reliable signal [source: blocked_reconciler.py#82-92].

## Default rule list

```python
DEFAULT_RULES = (
    ReconcileRule(
        name="patrol-passes",
        external_id_prefix="homelab-patrol-",
        target_state=PlaneState.DONE,
        min_pass_comments_since_fail=2,
        require_symphony_completion=False,
    ),
)
```

Ordered: first match wins. Adding a rule = adding an entry here. Default deployment ships **only** the patrol rule active. A fallback `symphony-completed-review` rule is intentionally left with an empty `external_id_prefix` for the comment template but a non-matching prefix so it cannot fire by accident — operator must edit this file or replace `DEFAULT_RULES` from the call site [source: blocked_reconciler.py#112-126].

## Skip conditions

The reconciler never touches Blocked issues that [source: blocked_reconciler.py#27-29]:

- lack a matching rule
- lack the required pass-count marker
- carry the `approval-required` label

## `ReconcileDecision` shape

Result of evaluating one Blocked issue [source: blocked_reconciler.py#136-146]:

```python
@dataclass(frozen=True)
class ReconcileDecision:
    issue_id: str
    identifier: str
    name: str
    external_id: str
    rule: ReconcileRule | None
    target_state: PlaneState | TrackerRole | None
    reason: str
    applied: bool = False
```

`applied=True` only when `apply=true` and the rule actually transitioned the issue.

## Env-driven runtime config

From `/home/james/symphony-host.env`:

| Var | Default | Effect |
|---|---|---|
| `SYMPHONY_BLOCKED_RECONCILER_ENABLED` | `true` | `false` disables scan entirely |
| `SYMPHONY_BLOCKED_RECONCILER_APPLY` | `false` | `false` logs decisions only; `true` mutates Plane |
| `SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS` | `1800000` (30 min) | scan interval; first tick after start runs scan immediately |

Per CLAUDE.md and [Symphony operations](symphony-operations.md#blocked-reconciler).

## Log markers

- `blocked_reconcile_skipped ... reason=no-pass-since-fail` — no current pass evidence since latest failure
- `blocked_reconcile_would_apply ... target_state=Done` — dry-run found candidate; review before apply
- `blocked_reconcile_applied ... target_state=Done` — apply mode moved ticket
- `blocked_reconcile_page_limit_reached`, `blocked_reconcile_comment_page_limit_reached` — cap hit; inspect manually before trusting totals

## Related

- [Symphony operations — Blocked Reconciler section](symphony-operations.md)
- C-0013, C-0014 (runtime defaults and evidence contract)
