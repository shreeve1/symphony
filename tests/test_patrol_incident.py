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


# ── Helpers ──────────────────────────────────────────────────────────────


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
    pending_severity: Severity | None = None,
    finding_changed: bool = False,
    dispatch_count: int = 1,
    active_run: bool = False,
    scheduled_hold: bool = False,
    recovery_confirmed: bool = False,
) -> RecurrenceInput:
    return RecurrenceInput(
        finding=finding or _finding(),
        issue_exists=issue_exists,
        issue_status=issue_status,
        last_dispatched_severity=last_dispatched_severity,
        pending_severity=pending_severity,
        finding_changed=finding_changed,
        dispatch_count=dispatch_count,
        active_run=active_run,
        scheduled_hold=scheduled_hold,
        recovery_confirmed=recovery_confirmed,
    )


# ── Table-driven: all issue states × scenarios ───────────────────────────
# Maps (status, scenario) → expected action


class TestTableDriven:
    """Coverage matrix: every IssueStatus × dispatch/severity/pass scenario."""

    # ── Active-run barrier ───────────────────────────────────────────
    def test_todo_active_run_escalation_queued(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            last_dispatched_severity=Severity.MEDIUM,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_running_active_run_escalation_queued(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.RUNNING,
            last_dispatched_severity=Severity.MEDIUM,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_in_review_active_run_escalation_queued(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.IN_REVIEW,
            last_dispatched_severity=Severity.MEDIUM,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_blocked_active_run_escalation_queued(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.BLOCKED,
            last_dispatched_severity=Severity.MEDIUM,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    # ── Done → always reopen ─────────────────────────────────────────
    def test_done_unchanged_reopens(self) -> None:
        inp = _input(
            issue_status=IssueStatus.DONE,
            finding_changed=False,
        )
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH

    def test_done_with_active_run_reopens(self) -> None:
        inp = _input(
            issue_status=IssueStatus.DONE,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH

    def test_done_with_hold_reopens(self) -> None:
        inp = _input(
            issue_status=IssueStatus.DONE,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH

    def test_done_pass_reopens(self) -> None:
        """Bugfix: pass on done is PASS_CONFIRMATION, not reopen."""
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_status=IssueStatus.DONE)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    # ── Archived → released lineage, create-new ──────────────────────
    def test_archived_creates_new(self) -> None:
        inp = _input(
            issue_status=IssueStatus.ARCHIVED,
            finding_changed=False,
        )
        assert decide(inp) is RecurrenceAction.CREATE_AND_DISPATCH

    # ── Pre-first-Run repeat → SILENT_UPDATE ─────────────────────────
    def test_todo_dispatch_count_zero_silent(self) -> None:
        inp = _input(
            issue_status=IssueStatus.TODO,
            dispatch_count=0,
            finding_changed=True,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_running_dispatch_count_zero_silent(self) -> None:
        inp = _input(
            issue_status=IssueStatus.RUNNING,
            dispatch_count=0,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_blocked_dispatch_count_zero_silent(self) -> None:
        inp = _input(
            issue_status=IssueStatus.BLOCKED,
            dispatch_count=0,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    # ── Scheduled hold is a dispatch barrier for escalation ──────────
    def test_todo_scheduled_hold_queues_escalation(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            last_dispatched_severity=Severity.MEDIUM,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_todo_scheduled_hold_stale_pending_silent(self) -> None:
        f = _finding(severity=Severity.MEDIUM)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            last_dispatched_severity=Severity.MEDIUM,
            pending_severity=Severity.HIGH,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    # ── Scheduled hold does NOT block recovery ───────────────────────
    def test_pass_scheduled_hold_recovery_allowed(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            recovery_confirmed=True,
            scheduled_hold=True,
            active_run=False,
        )
        assert decide(inp) is RecurrenceAction.RECOVERY_EVENT

    def test_pass_scheduled_hold_not_confirmed(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            recovery_confirmed=False,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    # ── Active run blocks recovery ───────────────────────────────────
    def test_pass_active_run_blocks_recovery(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            recovery_confirmed=True,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION


# ── CREATE_AND_DISPATCH ──────────────────────────────────────────────────


class TestDecideCreateAndDispatch:
    def test_first_detection_creates_new_issue(self) -> None:
        inp = _input(issue_exists=False, issue_status=None)
        assert decide(inp) is RecurrenceAction.CREATE_AND_DISPATCH


# ── SILENT_UPDATE ────────────────────────────────────────────────────────


class TestDecideSilentUpdate:
    def test_unchanged_finding_against_active_issue(self) -> None:
        assert decide(_input(finding_changed=False)) is RecurrenceAction.SILENT_UPDATE

    def test_evidence_changed_but_severity_not_worse(self) -> None:
        f = _finding(severity=Severity.LOW)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=Severity.MEDIUM,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_evidence_changed_same_severity(self) -> None:
        f = _finding(severity=Severity.MEDIUM)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=Severity.MEDIUM,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_de_escalated_lower_severity(self) -> None:
        f = _finding(severity=Severity.LOW)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.HIGH,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_dispatch_count_zero_pre_first_run(self) -> None:
        """Pre-first-Run: issue exists but no Run yet → silent update."""
        inp = _input(
            dispatch_count=0,
            finding_changed=True,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE


# ── Stale pending severity (de-escalated) ────────────────────────────────


class TestDecideStalePending:
    """A pending severity that no longer reflects the current finding must
    not produce a release (T.2.3)."""

    def test_stale_pending_after_de_escalation(self) -> None:
        """Current severity dropped below last_dispatched → stale pending."""
        f = _finding(severity=Severity.MEDIUM)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.HIGH,
            pending_severity=Severity.CRITICAL,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_stale_pending_at_last_dispatched_severity(self) -> None:
        f = _finding(severity=Severity.MEDIUM)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            pending_severity=Severity.CRITICAL,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_stale_pending_with_active_run(self) -> None:
        f = _finding(severity=Severity.MEDIUM)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.HIGH,
            pending_severity=Severity.CRITICAL,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_stale_pending_with_scheduled_hold(self) -> None:
        f = _finding(severity=Severity.MEDIUM)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.HIGH,
            pending_severity=Severity.CRITICAL,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.SILENT_UPDATE

    def test_valid_pending_same_severity(self) -> None:
        """pending=HIGH, current=HIGH, last=MEDIUM → release."""
        f = _finding(severity=Severity.HIGH)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            pending_severity=Severity.HIGH,
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE


# ── QUEUED_ESCALATION ────────────────────────────────────────────────────


class TestDecideQueuedEscalation:
    def test_severity_escalation_while_active_run(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_severity_escalation_while_hold(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_first_severity_set_while_active_run(self) -> None:
        f = _finding(severity=Severity.HIGH)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=None,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_valid_pending_still_queued_while_active_run(self) -> None:
        f = _finding(severity=Severity.HIGH)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            pending_severity=Severity.CRITICAL,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION

    def test_valid_pending_still_queued_while_hold(self) -> None:
        f = _finding(severity=Severity.HIGH)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            pending_severity=Severity.CRITICAL,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.QUEUED_ESCALATION


# ── ESCALATION_RELEASE ───────────────────────────────────────────────────


class TestDecideEscalationRelease:
    def test_severity_escalation_clear(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            finding_changed=True,
            last_dispatched_severity=Severity.MEDIUM,
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE

    def test_severity_escalation_no_finding_change(self) -> None:
        """Severity increase wins even when evidence text is unchanged."""
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            finding_changed=False,
            last_dispatched_severity=Severity.MEDIUM,
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE

    def test_valid_pending_now_clear(self) -> None:
        f = _finding(severity=Severity.HIGH)
        inp = _input(
            finding=f,
            last_dispatched_severity=Severity.MEDIUM,
            pending_severity=Severity.CRITICAL,
        )
        assert decide(inp) is RecurrenceAction.ESCALATION_RELEASE


# ── REOPEN_AND_DISPATCH ──────────────────────────────────────────────────


class TestDecideReopenAndDispatch:
    def test_done_issue_recurrence(self) -> None:
        inp = _input(issue_status=IssueStatus.DONE)
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH

    def test_done_no_other_state_matters(self) -> None:
        f = _finding(severity=Severity.CRITICAL)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.DONE,
            finding_changed=True,
            pending_severity=Severity.HIGH,
            active_run=True,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.REOPEN_AND_DISPATCH


# ── RECOVERY_EVENT ───────────────────────────────────────────────────────


class TestDecideRecoveryEvent:
    def test_confirmed_recovery_existing_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_exists=True,
            recovery_confirmed=True,
            active_run=False,
        )
        assert decide(inp) is RecurrenceAction.RECOVERY_EVENT

    def test_confirmed_recovery_no_active_run(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.TODO,
            recovery_confirmed=True,
            active_run=False,
        )
        assert decide(inp) is RecurrenceAction.RECOVERY_EVENT

    def test_confirmed_recovery_active_run_blocks(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_exists=True,
            recovery_confirmed=True,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_confirmed_recovery_no_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_exists=False,
            issue_status=None,
            recovery_confirmed=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_confirmed_recovery_done_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_exists=True,
            issue_status=IssueStatus.DONE,
            recovery_confirmed=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION


# ── PASS_CONFIRMATION ────────────────────────────────────────────────────


class TestDecidePassConfirmation:
    def test_confirmed_pass_archived_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_status=IssueStatus.ARCHIVED,
            recovery_confirmed=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_routine_pass_healthy(self) -> None:
        """Routine (non-confirmed) pass with existing issue → PASS."""
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=True, recovery_confirmed=False)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_routine_pass_no_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_exists=False, issue_status=None)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_routine_pass_done_issue(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(finding=f, issue_status=IssueStatus.DONE)
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_routine_pass_with_active_run(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_exists=True,
            recovery_confirmed=False,
            active_run=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION

    def test_routine_pass_with_scheduled_hold(self) -> None:
        f = _finding(is_pass=True)
        inp = _input(
            finding=f,
            issue_exists=True,
            recovery_confirmed=False,
            scheduled_hold=True,
        )
        assert decide(inp) is RecurrenceAction.PASS_CONFIRMATION
