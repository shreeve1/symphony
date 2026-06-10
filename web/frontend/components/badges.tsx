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
