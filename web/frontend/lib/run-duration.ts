import type { Run } from "@/lib/api";
import { isActiveRunState } from "@/lib/polling";

function formatSeconds(totalSeconds: number) {
	const safeSeconds = Math.max(0, totalSeconds);
	const hours = Math.floor(safeSeconds / 3600);
	const minutes = Math.floor((safeSeconds % 3600) / 60);
	const seconds = safeSeconds % 60;
	if (hours > 0) return `${hours}h${minutes}m${seconds}s`;
	if (minutes > 0) return `${minutes}m${seconds}s`;
	return `${seconds}s`;
}

function elapsedSeconds(startedAt: string, endedAt: string | number) {
	const started = Date.parse(startedAt);
	const ended = typeof endedAt === "number" ? endedAt : Date.parse(endedAt);
	const ms = ended - started;
	if (!Number.isFinite(ms) || ms < 0) return null;
	return Math.floor(ms / 1000);
}

export function formatRunDuration(
	run: Pick<Run, "state" | "started_at" | "ended_at"> | null | undefined,
	nowMs = Date.now(),
) {
	if (!run?.started_at) return "—";
	if (run.ended_at) {
		const seconds = elapsedSeconds(run.started_at, run.ended_at);
		return seconds == null ? "—" : formatSeconds(seconds);
	}
	if (!isActiveRunState(run.state)) return "—";
	const seconds = elapsedSeconds(run.started_at, nowMs);
	return seconds == null ? "—" : `running ${formatSeconds(seconds)}`;
}

export function isLiveElapsedRun(
	run: Pick<Run, "state" | "started_at" | "ended_at"> | null | undefined,
) {
	return Boolean(run?.started_at && !run.ended_at && isActiveRunState(run.state));
}
