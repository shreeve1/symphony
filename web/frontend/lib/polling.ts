import type { Issue, Run } from "@/lib/api";

const ACTIVE_RUN_STATES = new Set(["queued", "running"]);

export function isActiveRunState(state: string | null | undefined) {
	return state != null && ACTIVE_RUN_STATES.has(state);
}

export function hasActiveIssue(issues: Issue[] | undefined) {
	return (issues ?? []).some(
		(issue) =>
			issue.state === "running" || isActiveRunState(issue.latest_run_state),
	);
}

export function issueListRefetchIntervalMs(issues: Issue[] | undefined) {
	return hasActiveIssue(issues) ? 3_000 : 10_000;
}

export function issueDetailRefetchIntervalMs(
	issue: Pick<Issue, "state" | "latest_run_state"> | null | undefined,
) {
	if (!issue) return false;
	return issue.state === "todo" ||
		issue.state === "running" ||
		isActiveRunState(issue.latest_run_state)
		? 3_000
		: false;
}

export function runListRefetchIntervalMs(
	runs: Pick<Run, "state">[] | undefined,
) {
	return (runs ?? []).some((run) => isActiveRunState(run.state))
		? 3_000
		: false;
}

export function runDetailRefetchIntervalMs(
	run: Pick<Run, "state"> | null | undefined,
) {
	return isActiveRunState(run?.state) ? 3_000 : false;
}
