import { cn } from "@/lib/utils";

const PRIORITY_STYLE: Record<string, string> = {
	urgent: "bg-red-100 text-red-700 border-red-200",
	high: "bg-orange-100 text-orange-700 border-orange-200",
	med: "bg-amber-100 text-amber-700 border-amber-200",
	low: "bg-slate-100 text-slate-600 border-slate-200",
};

export function PriorityBadge({ priority }: { priority: string | null }) {
	if (!priority) return null;
	return (
		<span
			data-testid="priority-badge"
			className={cn(
				"rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
				PRIORITY_STYLE[priority] ?? PRIORITY_STYLE.low,
			)}
		>
			{priority}
		</span>
	);
}

const VERDICT_STYLE: Record<string, string> = {
	done: "bg-emerald-100 text-emerald-700",
	review: "bg-amber-100 text-amber-700",
	blocked: "bg-red-100 text-red-700",
};

export function VerdictPill({ verdict }: { verdict: string | null }) {
	if (!verdict) return null;
	return (
		<span
			data-testid="verdict-pill"
			className={cn(
				"rounded-full px-2 py-0.5 text-[10px] font-medium",
				VERDICT_STYLE[verdict] ?? "bg-muted text-muted-foreground",
			)}
		>
			{verdict}
		</span>
	);
}

// Issue #461: surface the issue's origin so automation-spawned issues are
// visually distinct from operator and patrol ones. Operator rows render
// nothing — operator is the default and a chip on every row would be noise.
const ORIGIN_STYLE: Record<string, string> = {
	patrol: "bg-violet-100 text-violet-700 border-violet-200",
	automation: "bg-sky-100 text-sky-700 border-sky-200",
};

export function OriginChip({ origin }: { origin: string }) {
	if (!origin || origin === "operator") return null;
	return (
		<span
			data-testid="origin-chip"
			className={cn(
				"rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
				ORIGIN_STYLE[origin] ?? "bg-muted text-muted-foreground border-muted",
			)}
			title={`Origin: ${origin}`}
		>
			{origin}
		</span>
	);
}
