export type ScheduleMode = "next_window" | "custom" | "none";

export interface ScheduleDraft {
	mode: ScheduleMode;
	custom: string;
	reason: string;
}

export interface ScheduleRequestBody {
	not_before: string;
	reason: string;
}

export const DEFAULT_SCHEDULE_REASON = "operator scheduled via Podium";

export const defaultScheduleDraft = (): ScheduleDraft => ({
	mode: "next_window",
	custom: "",
	reason: DEFAULT_SCHEDULE_REASON,
});

function pad(value: number) {
	return String(value).padStart(2, "0");
}

function localDateTimeWithOffset(value: string): string | null {
	const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
	if (!match) return null;
	const [, y, m, d, hh, mm] = match;
	const date = new Date(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm));
	if (Number.isNaN(date.getTime())) return null;
	const offset = -date.getTimezoneOffset();
	const sign = offset >= 0 ? "+" : "-";
	const abs = Math.abs(offset);
	return `${value}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

export function schedulePayloadFromDraft(
	draft: ScheduleDraft,
): ScheduleRequestBody | null {
	if (draft.mode === "none") return null;
	const reason = draft.reason.trim() || DEFAULT_SCHEDULE_REASON;
	if (draft.mode === "next_window") return { not_before: "next_window", reason };
	const notBefore = localDateTimeWithOffset(draft.custom);
	return notBefore ? { not_before: notBefore, reason } : null;
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
					<span className="text-xs font-medium text-muted-foreground">Schedule</span>
					<select
						data-testid={`${testid}-mode`}
						value={draft.mode}
						disabled={disabled}
						onChange={(e) => update({ mode: e.target.value as ScheduleMode })}
						className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
					>
						<option value="next_window">Next maintenance window</option>
						<option value="custom">Custom date-time</option>
						<option value="none">None</option>
					</select>
				</label>
				{currentNotBefore && (
					<p data-testid={`${testid}-current`} className="text-xs text-muted-foreground">
						Scheduled for {currentNotBefore}
					</p>
				)}
			</div>
			{draft.mode === "custom" && (
				<label className="block space-y-1">
					<span className="text-xs font-medium text-muted-foreground">Custom date-time</span>
					<input
						type="datetime-local"
						data-testid={`${testid}-custom`}
						value={draft.custom}
						disabled={disabled}
						onChange={(e) => update({ custom: e.target.value })}
						className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
					/>
				</label>
			)}
			{draft.mode !== "none" && (
				<label className="block space-y-1">
					<span className="text-xs font-medium text-muted-foreground">Reason</span>
					<input
						data-testid={`${testid}-reason`}
						value={draft.reason}
						disabled={disabled}
						onChange={(e) => update({ reason: e.target.value })}
						className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
					/>
				</label>
			)}
		</div>
	);
}
