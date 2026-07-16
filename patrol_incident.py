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
    escalation_pending: bool
    finding_changed: bool
    dispatch_blocked: bool


def decide(input: RecurrenceInput) -> RecurrenceAction:
    """Pure decision function for patrol incident recurrence.

    Produces one of the seven :class:`RecurrenceAction` values based on
    finding type, issue state, severity comparison, and dispatch barriers.
    """
    f = input.finding

    # ── Pass (healthy) findings ──────────────────────────────────────────
    if f.is_pass:
        if (
            input.issue_exists
            and input.issue_status is not IssueStatus.DONE
            and not input.dispatch_blocked
        ):
            return RecurrenceAction.RECOVERY_EVENT
        return RecurrenceAction.PASS_CONFIRMATION

    # ── No issue yet → create new ────────────────────────────────────────
    if not input.issue_exists:
        return RecurrenceAction.CREATE_AND_DISPATCH

    # ── Done → reopen ────────────────────────────────────────────────────
    if input.issue_status is IssueStatus.DONE:
        return RecurrenceAction.REOPEN_AND_DISPATCH

    # ── Active issue (Todo / Running / InReview / Blocked) ───────────────
    # Severity escalation — check before finding_changed so a severity
    # increase is never silently swallowed.
    current_rank = f.severity.rank
    last_rank = (
        input.last_dispatched_severity.rank if input.last_dispatched_severity else 0
    )
    if current_rank > last_rank:
        if input.dispatch_blocked:
            return RecurrenceAction.QUEUED_ESCALATION
        return RecurrenceAction.ESCALATION_RELEASE

    # Pending escalation still blocked
    if input.escalation_pending and input.dispatch_blocked:
        return RecurrenceAction.QUEUED_ESCALATION

    # Pending escalation cleared → release
    if input.escalation_pending and not input.dispatch_blocked:
        return RecurrenceAction.ESCALATION_RELEASE

    # Finding unchanged → silent
    if not input.finding_changed:
        return RecurrenceAction.SILENT_UPDATE

    # Evidence changed but not an escalation
    return RecurrenceAction.SILENT_UPDATE
