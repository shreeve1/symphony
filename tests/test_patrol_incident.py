"""Focused pure-contract tests for patrol_incident recurrence decision."""

from __future__ import annotations

from patrol_incident import (
    Finding,
    IncidentKey,
    IssueStatus,
    RecurrenceAction,
    RecurrenceInput,
    Severity,
    decide,
    derive_key,
)


# ── Severity ranking ─────────────────────────────────────────────────────


class TestSeverityRanking:
    def test_critical_is_highest(self) -> None:
        assert Severity.CRITICAL.rank == 5
        assert Severity.CRITICAL.rank > Severity.HIGH.rank

    def test_high_ranks_above_medium(self) -> None:
        assert Severity.HIGH.rank == 4
        assert Severity.HIGH.rank > Severity.MEDIUM.rank

    def test_medium_ranks_above_low(self) -> None:
        assert Severity.MEDIUM.rank == 3
        assert Severity.MEDIUM.rank > Severity.LOW.rank

    def test_low_ranks_above_informational(self) -> None:
        assert Severity.LOW.rank == 2
        assert Severity.LOW.rank > Severity.INFORMATIONAL.rank

    def test_informational_is_lowest(self) -> None:
        assert Severity.INFORMATIONAL.rank == 1


# ── Incident key derivation ──────────────────────────────────────────────


class TestDeriveKey:
    def test_present_labels_produce_key(self) -> None:
        key = derive_key("disk", "nas1:/data")
        assert key == IncidentKey(family="disk", resource="nas1:/data")

    def test_missing_family_returns_none(self) -> None:
        assert derive_key(None, "nas1:/data") is None

    def test_missing_resource_returns_none(self) -> None:
        assert derive_key("disk", None) is None

    def test_empty_family_returns_none(self) -> None:
        assert derive_key("", "nas1:/data") is None

    def test_empty_resource_returns_none(self) -> None:
        assert derive_key("disk", "") is None

    def test_both_missing_returns_none(self) -> None:
        assert derive_key(None, None) is None


# ── Recurrence decision ──────────────────────────────────────────────────


def _finding(
    severity: Severity = Severity.MEDIUM,
    is_pass: bool = False,
) -> Finding:
    return Finding(
        severity=severity,
        incident_family="disk",
        incident_resource="nas1:/data",
        evidence="98% full",
        is_pass=is_pass,
    )


def _input(
    finding: Finding | None = None,
    issue_exists: bool = True,
    issue_status: IssueStatus | None = IssueStatus.TODO,
    last_dispatched_severity: Severity | None = Severity.MEDIUM,
    escalation_pending: bool = False,
    finding_changed: bool = False,
    dispatch_blocked: bool = False,
) -> RecurrenceInput:
    return RecurrenceInput(
        finding=finding or _finding(),
        issue_exists=issue_exists,
        issue_status=issue_status,
        last_dispatched_severity=last_dispatched_severity,
        escalation_pending=escalation_pending,
        finding_changed=finding_changed,
        dispatch_blocked=dispatch_blocked,
    )


class TestDecideCreateAndDispatch:
    def test_first_detection_creates_new_issue(self) -> None:
        inp = _input(issue_exists=False, issue_status=None)
        assert decide(inp) is RecurrenceAction.CREATE_AND_DISPATCH


class TestDecideSilentUpdate:
    def test_unchanged_finding_against_active_issue(self) -> None:
        assert decide(_input(finding_changed=False)) is RecurrenceAction.SILENT_UPDATE

    def test_evidence_changed_but_severity_not_worse(self) -> None:
        f = _finding(severity=Severity.LOW)  # lower than last dispatched
        inp = _input(
            finding=f, finding_changed=True, last_dispatched_severity=Severity.MEDIUM
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_evidence_changed_same_severity(self) -> None:
        f = _finding(severity=Severity.MEDIUM)  # same as last
        inp = _input(
            finding=f, finding_changed=True, last_dispatched_severity=Severity.MEDIUM
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE


class TestDecideEscalationOverridesUnchangedFinding:
    """Bugfix: severity escalation must not be suppressed by finding_changed=False."""

    def test_severity_escalation_no_finding_change(self) -> None:
        """Severity increase wins even when evidence text is unchanged."""
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            finding_changed=False,
            last_dispatched_severity=Severity.MEDIUM,
            dispatch_blocked=False,
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE

    def test_severity_escalation_no_finding_change_blocked(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            finding_changed=False,
            last_dispatched_severity=Severity.MEDIUM,
            dispatch_blocked=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION


class TestDecideQueuedEscalation:
    def test_severity_escalation_while_dispatch_blocked(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=Severity.MEDIUM,
            dispatch_blocked=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_first_severity_set_while_dispatch_blocked(self) -> None:
        """No last dispatched severity + blocked → queued."""
        f = _finding(severity=Severity.HIGH)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=None,
            dispatch_blocked=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION


class TestDecideBlockedEscalationPending:
    """Bugfix: pending escalation while still blocked must not be silently updated."""

    def test_escalation_pending_still_blocked_finding_unchanged(self) -> None:
        inp = _input(
            finding_changed=False,
            escalation_pending=True,
            dispatch_blocked=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_escalation_pending_still_blocked_finding_changed(self) -> None:
        f = _finding(severity=Severity.LOW)
        inp = _input(
            finding=f,
            finding_changed=True,
            escalation_pending=True,
            dispatch_blocked=True,
            last_dispatched_severity=Severity.LOW,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION


class TestDecideEscalationRelease:
    def test_escalation_pending_now_clear(self) -> None:
        inp = _input(
            finding_changed=False, escalation_pending=True, dispatch_blocked=False
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE

    def test_severity_escalation_no_blockers(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=Severity.MEDIUM,
            dispatch_blocked=False,
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE


class TestDecideReopenAndDispatch:
    def test_done_issue_recurrence(self) -> None:
        inp = _input(issue_status=IssueStatus.DONE)
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH

    def test_done_no_other_state_matters(self) -> None:
        """Done beats escalation-pending, finding-changed, etc."""
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.DONE,
            finding_changed=True,
            escalation_pending=True,
            dispatch_blocked=True,
        )
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH


class TestDecideRecoveryEvent:
    def test_pass_finding_with_existing_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=True)
        assert decide(inp) is RecurrenceAction.RECOVERY_EVENT

    def test_pass_finding_with_done_issue(self) -> None:
        """Bugfix: pass on a done issue is PASS_CONFIRMATION, not recovery."""
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=True, issue_status=IssueStatus.DONE)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_pass_finding_with_dispatch_blocked(self) -> None:
        """Bugfix: pass on a dispatch-blocked issue is PASS_CONFIRMATION, not recovery."""
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=True, dispatch_blocked=True)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION


class TestDecidePassConfirmation:
    def test_pass_finding_with_no_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=False, issue_status=None)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_pass_finding_healthy_still_healthy(self) -> None:
        """No issue means no prior failure to recover from."""
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=False, issue_status=None)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION
