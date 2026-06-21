export type ScheduleMode = "next_window" | "none";

export interface ScheduleDraft {
	mode: ScheduleMode;
	reason: string;
}

export interface ScheduleRequestBody {
	not_before: string;
	reason: string;
}

export const DEFAULT_SCHEDULE_REASON = "operator scheduled via Podium";

export const defaultScheduleDraft = (): ScheduleDraft => ({
	mode: "none",
	reason: DEFAULT_SCHEDULE_REASON,
});

export function schedulePayloadFromDraft(
	draft: ScheduleDraft,
): ScheduleRequestBody | null {
	if (draft.mode === "none") return null;
	const reason = draft.reason.trim() || DEFAULT_SCHEDULE_REASON;
	// "Yes" always schedules for the next maintenance window; the scheduler
	// resolves the symbolic next_window to the window start (00:00 PT).
	return { not_before: "next_window", reason };
}

export function latestScheduleNotBefore(comments: string): string | null {
	const lines = comments.split(/\r?\n/).reverse();
	for (const line of lines) {
		if (line.startsWith("Symphony-Schedule-Cancelled:")) return null;
		const match = /^Symphony-Schedule:\s+.*\bnot_before=([^\s]+).*/.exec(line);
		if (match) return match[1];
	}
	return null;
}

export function ScheduleControl({
	draft,
	onChange,
	testid,
	currentNotBefore,
	disabled = false,
}: {
	draft: ScheduleDraft;
	onChange: (draft: ScheduleDraft) => void;
	testid: string;
	currentNotBefore?: string | null;
	disabled?: boolean;
}) {
	const update = (patch: Partial<ScheduleDraft>) =>
		onChange({ ...draft, ...patch });
	return (
		<div className="space-y-2 rounded-md border p-3" data-testid={testid}>
			<div className="flex items-center justify-between gap-2">
				<label className="flex-1 space-y-1">
					<span className="text-xs font-medium text-muted-foreground">
						Schedule for next maintenance window
					</span>
					<select
						data-testid={`${testid}-mode`}
						value={draft.mode}
						disabled={disabled}
						onChange={(e) => update({ mode: e.target.value as ScheduleMode })}
						className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
					>
						<option value="none">No</option>
						<option value="next_window">Yes</option>
					</select>
				</label>
				{currentNotBefore && (
					<p data-testid={`${testid}-current`} className="text-xs text-muted-foreground">
						Scheduled for {currentNotBefore}
					</p>
				)}
			</div>
		</div>
	);
}
