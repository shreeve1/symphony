"""Pure patrol incident identity, severity, and recurrence decision logic.

No side effects, no I/O, no imports from ``web.*`` or ``tracker_*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class Severity(Enum):
    """Ordered severity levels. Higher value = more severe."""

    INFORMATIONAL = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5

    @property
    def rank(self) -> int:
        return self.value


# ---------------------------------------------------------------------------
# Incident identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class IncidentKey:
    """Deterministic identity for an incident, derived from alert labels."""

    family: str
    resource: str


def derive_key(
    incident_family: str | None,
    incident_resource: str | None,
) -> IncidentKey | None:
    """Derive an :class:`IncidentKey` from explicit alert labels.

    Returns *None* when either label is missing, so uncertain findings never
    collapse into an existing incident (fail safe, never over-merge).
    """
    if not incident_family or not incident_resource:
        return None
    return IncidentKey(family=incident_family, resource=incident_resource)


# ---------------------------------------------------------------------------
# Recurrence inputs / actions
# ---------------------------------------------------------------------------


class IssueStatus(Enum):
    TODO = auto()
    RUNNING = auto()
    IN_REVIEW = auto()
    BLOCKED = auto()
    DONE = auto()
    ARCHIVED = auto()


class RecurrenceAction(Enum):
    """Exhaustive actions a recurrence decision can produce."""

    CREATE_AND_DISPATCH = auto()
    SILENT_UPDATE = auto()
    QUEUED_ESCALATION = auto()
    ESCALATION_RELEASE = auto()
    REOPEN_AND_DISPATCH = auto()
    RECOVERY_EVENT = auto()
    PASS_CONFIRMATION = auto()


@dataclass(frozen=True)
class Finding:
    """A single patrol observation."""

    severity: Severity
    incident_family: str
    incident_resource: str
    evidence: str
    is_pass: bool = False


@dataclass(frozen=True)
class RecurrenceInput:
    """All inputs needed for a pure recurrence decision."""

    finding: Finding
    issue_exists: bool
    issue_status: IssueStatus | None
    last_dispatched_severity: Severity | None
    pending_severity: Severity | None = None
    finding_changed: bool = False
    dispatch_count: int = 0
    active_run: bool = False
    scheduled_hold: bool = False
    recovery_confirmed: bool = False


def decide(input: RecurrenceInput) -> RecurrenceAction:
    """Pure decision function for patrol incident recurrence.

    Produces one of the seven :class:`RecurrenceAction` values based on
    finding type, issue state, severity comparison, and dispatch barriers.
    """
    f = input.finding

    # ── Pass (healthy) findings ──────────────────────────────────────────
    if f.is_pass:
        if (
            input.recovery_confirmed
            and input.issue_exists
            and input.issue_status not in (IssueStatus.DONE, IssueStatus.ARCHIVED)
            and not input.active_run
        ):
            return RecurrenceAction.RECOVERY_EVENT
        return RecurrenceAction.PASS_CONFIRMATION

    # ── No issue yet → create new ────────────────────────────────────────
    if not input.issue_exists:
        return RecurrenceAction.CREATE_AND_DISPATCH

    # ── Done / Archived → reopen / create-new ────────────────────────────
    if input.issue_status is IssueStatus.DONE:
        return RecurrenceAction.REOPEN_AND_DISPATCH

    if input.issue_status is IssueStatus.ARCHIVED:
        return RecurrenceAction.CREATE_AND_DISPATCH

    # ── Pre-first-Run: already created but no Run yet → silent update ────
    if input.dispatch_count == 0:
        return RecurrenceAction.SILENT_UPDATE

    # ── Active issue (Todo / Running / InReview / Blocked) ───────────────
    dispatch_blocked = input.active_run or input.scheduled_hold

    # Severity escalation
    current_rank = f.severity.rank
    last_rank = (
        input.last_dispatched_severity.rank if input.last_dispatched_severity else 0
    )

    if current_rank > last_rank:
        if dispatch_blocked:
            return RecurrenceAction.QUEUED_ESCALATION
        return RecurrenceAction.ESCALATION_RELEASE

    # A pending severity is historical bookkeeping only. Once the latest
    # observation no longer exceeds the last dispatched severity, it is stale.
    # Finding unchanged or not an escalation → silent.
    return RecurrenceAction.SILENT_UPDATE
