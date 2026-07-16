# Patrol Incident Deduplication and Bounded History

## Problem Statement

Homelab patrol and alert-forwarder findings can represent the same underlying incident under different alert names or severity thresholds. Podium currently deduplicates only exact external IDs, so related threshold alerts can create separate issues and dispatch separate agents.

Exact recurring findings are also costly. A repeated failure updates its existing issue, appends another comment, moves the issue back to Todo, and triggers another agent run. One live disk issue accumulated hundreds of runs, tens of millions of input tokens, and hundreds of thousands of comment characters while the underlying condition remained unchanged. Retaining or deleting Run rows alone does not solve this because dispatch behavior, comments, and native agent-session continuity are separate token inputs.

The operator needs one stable issue per active incident, no agent redispatch for unchanged evidence, bounded patrol history, and an explicit way to end an incident lineage. Moving a patrol issue to Archive must sever its dedup identity so a later recurrence creates a fresh issue and fresh agent session. Moving it to Done must retain identity so recurrence reopens the canonical issue.

## Solution

Treat a patrol finding as an **Incident** identified deterministically by an explicit incident family and resource. Coalesce simultaneous findings for the same Incident, retain the highest-severity finding as canonical, and never use fuzzy title matching or an LLM to decide identity.

For an existing active Incident, unchanged recurring evidence updates the issue's current evidence, last-seen timestamp, and occurrence count in place. It does not append a comment, change the issue to Todo, or dispatch an agent. A new agent run is allowed only for first detection, severity escalation, or explicit operator reply, and concurrent runs for one Incident are forbidden.

Keep only the latest three patrol Run rows and their logs. Rotate patrol agent continuity so an allowed dispatch cannot reattach native session context older than the same three-run horizon. Non-patrol issue history is unchanged.

Archive is the explicit lineage boundary. Archiving a patrol issue atomically releases its active dedup key while preserving historical incident metadata in the archived issue. The next matching finding creates a new issue and session. Done is not a lineage boundary: a matching recurrence reopens the existing issue.

## User Stories

1. As an operator, I want one active issue per underlying infrastructure incident, so that I do not review duplicate tickets.
2. As an operator, I want disk warning and critical thresholds for the same filesystem to share one Incident, so that severity thresholds do not create competing tickets.
3. As an operator, I want the highest-severity simultaneous finding to become canonical, so that the board shows the most urgent state.
4. As an operator, I want deterministic matching, so that I can understand why findings were combined.
5. As an operator, I want distinct resources to remain distinct, so that a failure on one host or mountpoint never hides another.
6. As an operator, I want unannotated alert series to retain exact per-series identity, so that rollout does not accidentally collapse unrelated findings.
7. As an operator, I want unchanged recurring evidence to update one issue silently, so that a one-minute poll does not produce one-minute comments.
8. As an operator, I want the issue to show current evidence, so that silent recurrence does not leave stale diagnostics.
9. As an operator, I want to see when the incident was last observed, so that I know whether it is still current.
10. As an operator, I want to see an occurrence count, so that persistence is visible without a wall of comments.
11. As an operator, I want unchanged recurrence to preserve the issue state, so that In Review and Blocked findings are not automatically moved back to Todo.
12. As an operator, I want unchanged recurrence to create no agent run, so that persistent faults do not burn tokens repeatedly.
13. As an operator, I want the first detection to dispatch an agent, so that new incidents still receive automated attention.
14. As an operator, I want a severity escalation to dispatch one additional agent, so that materially worse conditions receive renewed attention.
15. As an operator, I want multiple escalation observations during an active run to coalesce into one pending escalation, so that an Incident never has concurrent agents.
16. As an operator, I want an operator reply to remain an explicit redispatch action, so that I control when an agent revisits an unresolved Incident.
17. As an operator, I want a recovered Incident to record a concise recovery event, so that closure remains auditable.
18. As an operator, I want routine passing polls to remain silent, so that recovery confirmation does not create repetitive comments.
19. As an operator, I want Done findings to retain their identity, so that a recurrence reopens the known Incident rather than fragmenting history.
20. As an operator, I want Archive to sever Incident identity, so that I can deliberately start a clean lineage.
21. As an operator, I want archived history preserved, so that severing identity does not erase prior evidence or decisions.
22. As an operator, I want a recurrence after Archive to receive a new issue ID, so that it also receives a fresh agent session.
23. As an operator, I want only the latest three patrol Run rows visible, so that recurring issues remain manageable.
24. As an operator, I want logs older than the latest three patrol Runs removed with their rows, so that stale execution artifacts do not accumulate.
25. As an operator, I want the issue's latest-run projection to remain valid after pruning, so that Podium never points at a deleted Run.
26. As an operator, I want active Runs protected from retention, so that pruning cannot corrupt in-flight work.
27. As an operator, I want non-patrol Run history unchanged, so that coding and manually authored issues retain their existing audit behavior.
28. As an operator, I want patrol agent sessions rotated at the three-run boundary, so that retained database history and model context have the same ceiling.
29. As an operator, I want a fresh patrol session to receive current bounded issue state, so that rotation does not lose actionable evidence.
30. As an operator, I want comments only for first detection, escalation, recovery, and operator action, so that the conversation remains meaningful.
31. As an operator, I want deterministic fallback behavior when incident labels are missing, so that malformed or legacy alerts fail safe rather than over-deduplicate.
32. As an operator, I want priority and title to follow the canonical highest-severity finding, so that escalation is visible on the board.
33. As an operator, I want lower-severity evidence preserved in the current Incident state without separate dispatch, so that coalescing does not hide useful context.
34. As an operator, I want retention to clean up existing patrol issues with excessive history, so that the benefit applies to current incidents as well as new ones.
35. As an operator, I want measurable counters for created, coalesced, silently updated, escalated, and pruned events, so that the new policy can be verified in production.
36. As an operator, I want the alert-forwarder schedule to remain operational during separate forwarder work, so that this PRD does not impose an unrequested pause.

## Implementation Decisions

- Introduce a pure **Incident Coalescer** as a deep, independently testable module. Its input is a set of normalized findings; its output is one canonical finding per deterministic Incident identity.
- Incident identity is the tuple of `incident_family` and `incident_resource`. Alert rules supply these explicit values for related thresholds. The resource includes the stable dimensions that distinguish affected infrastructure, such as host and mountpoint.
- Findings without explicit Incident identity fall back to the existing alert-name and per-series fingerprint behavior. Missing metadata must increase separation, never collapse uncertain findings.
- The Incident Coalescer ranks severities in the existing order: critical, high, medium, low, informational. The highest severity wins; deterministic tie-breaking makes repeated polls stable.
- Introduce a pure **Patrol Recurrence Policy** as a second deep module. It decides among create-and-dispatch, silent update, queued escalation, reopen-and-dispatch, and recovery based on issue state, current severity, last-dispatched severity, and active-run state.
- First detection creates a Todo issue and permits one dispatch.
- An unchanged finding against an active Todo, Running, In Review, or Blocked issue updates current evidence, `last_seen_at`, and occurrence count without appending a comment or changing state.
- Severity is compared with the last severity that received a dispatch, not merely the latest observed severity. This preserves a pending escalation while another run is active.
- Escalation permits exactly one additional dispatch. If a run is active, escalation remains pending and is released only after the active run completes; concurrent dispatch is forbidden.
- Operator Reply remains the explicit human-controlled redispatch mechanism.
- Done retains the active Incident identity. A recurrence reopens the canonical issue to Todo and permits one dispatch.
- Archive is the only operator state transition that severs patrol identity. Archiving atomically clears the row's active external dedup key while preserving the former identity in historical incident metadata.
- A recurrence after Archive uses the released deterministic key to create a new issue. The new issue ID naturally creates a new issue-scoped agent session.
- Archived issues are excluded from active forwarder reconciliation and close-by-absence scans.
- Current evidence is replacement state, not an append-only event stream. The issue description carries the latest diagnostic plus durable Incident metadata, including first seen, last seen, occurrence count, current severity, and last-dispatched severity.
- Comments are emitted only for first detection, severity escalation, recovery/closure, and operator action. Routine repeated failure and routine pass confirmation do not append comments.
- Patrol Run retention applies only to issues whose origin is patrol. Keep the newest three Run rows by Run order and their logs; delete older patrol Run logs and rows.
- Retention never deletes queued or running Runs and never invalidates the issue's latest-run reference. Non-patrol retention remains unchanged.
- Patrol native agent continuity is bounded to three Runs. A fourth allowed dispatch starts a fresh native session with current bounded issue state rather than reattaching older session history.
- Audit retention and token control are separate protections: retention bounds stored history, while recurrence policy prevents unnecessary dispatch and comment growth.
- Existing patrol issues are eligible for the new retention policy without changing their issue identity or current state.
- Expose structured operational counts for coalescing, silent updates, escalations, archive severance, and Run pruning. Do not log full diagnostics or secrets.
- Roll out cross-repository behavior in dependency order: deterministic identity/coalescing and recurrence policy first, Podium archive/retention contracts second, then live forwarder verification.

## Testing Decisions

- Tests assert externally visible behavior and stable contracts, not helper call order or private implementation structure.
- The Incident Coalescer receives focused table-driven unit tests because it is the primary correctness boundary for avoiding both duplicate work and false collapse.
- Coalescer tests cover warning/critical thresholds for one resource, equal-severity ties, distinct hosts, distinct mountpoints, distinct incident families, shuffled input order, and missing identity fallback.
- The Patrol Recurrence Policy receives matrix tests across Todo, Running, In Review, Blocked, Done, and Archived states; unchanged, escalated, and recovered observations; and active versus inactive Runs.
- Recurrence tests prove that unchanged active findings create no comment, no state transition, and no dispatch.
- Escalation tests prove that one escalation creates at most one additional dispatch and that repeated observations during an active run remain coalesced.
- Done-versus-Archive contract tests prove that Done reopens the same issue while Archive releases the key and causes the next recurrence to create a different issue.
- Archive API tests verify that identity release and state transition are atomic and that the historical marker remains readable.
- Forwarder workflow tests use mocked alert payloads to prove one issue for related thresholds, separate issues for distinct resources, and safe fallback for unannotated alerts.
- Recovery tests verify one concise recovery event and no repetitive pass comments.
- Retention integration tests seed more than three patrol Runs, execute retention, and verify that exactly the newest three rows/logs remain.
- Retention tests verify foreign-key integrity, valid latest-run projection, active-Run preservation, and unchanged non-patrol history.
- Session-continuity tests prove that patrol context never crosses the three-run horizon and that the rotated session receives current issue evidence.
- End-to-end tests cover first detection, silent recurrence, escalation, operator reply, recovery, Done recurrence, Archive recurrence, and retention.
- Existing tracker, log-retention, issue-state patch, prompt-rendering, and alert-forwarder tests are prior art and must remain green.
- Live verification uses two controlled alert thresholds on one disposable resource: one canonical issue, one initial dispatch, silent repeated polls, one escalation dispatch, and a fresh issue after Archive.
- Production verification records issue count, Run count, comment growth, and token usage before and after rollout without exposing diagnostic payloads.

## Out of Scope

- Fuzzy title, description, embedding, or LLM-based duplicate detection.
- Automatic root-cause inference across unrelated incident families.
- Deduplication of operator-authored or coding issues.
- Merging historical duplicate issues into one row.
- Rewriting historical comments or summaries.
- Changing Done into a lineage boundary.
- Pausing the alert-forwarder schedule as part of this PRD.
- Redesigning general Podium retention for non-patrol issues.
- Changing alert detection thresholds or remediation logic except where explicit Incident identity labels are required.
- Building a general event-sourcing system for issue history.

## Further Notes

- The observed failure has two independent causes: related alert series receive different exact IDs, and exact recurring findings repeatedly reopen their issue. Both must be fixed; coalescing alone does not stop repeat Runs.
- Run-row deletion alone cannot reduce model input when a recurring issue keeps dispatching or reuses an old native session. The recurrence and continuity rules are therefore mandatory acceptance criteria, not optional cleanup.
- Explicit Incident identity is intentionally conservative. A false negative creates an extra issue; a false positive can hide a distinct infrastructure failure. Uncertain findings must remain separate.
- The current 12,000-character fresh-prompt comment cap remains useful defense in depth, but it is not a substitute for bounded stored history and silent recurrence.
- This PRD captures the decisions from issue 421's completed grilling session. Implementation must coordinate with concurrent alert-forwarder work to avoid overlapping edits.
