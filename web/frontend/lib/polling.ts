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

export function runDetailRefetchIntervalMs(
	run: Pick<Run, "state"> | null | undefined,
) {
	return isActiveRunState(run?.state) ? 3_000 : false;
}
