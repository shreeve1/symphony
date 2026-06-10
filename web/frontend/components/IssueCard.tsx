import type { Issue } from "@/lib/api";
import { formatAge } from "@/lib/issues";
import { PriorityBadge, VerdictPill } from "@/components/badges";

// A single board card: title, priority badge, latest verdict pill, age.
export function IssueCard({
  issue,
  onClick,
}: {
  issue: Issue;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid="issue-card"
      onClick={onClick}
      className="w-full rounded-lg border bg-background p-3 text-left shadow-sm transition hover:border-foreground/30 hover:shadow"
    >
      <p className="text-sm font-medium leading-snug">{issue.title}</p>
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <PriorityBadge priority={issue.priority} />
          <VerdictPill verdict={issue.latest_verdict} />
        </div>
        <span className="text-[11px] text-muted-foreground">
          {formatAge(issue.last_event_at)}
        </span>
      </div>
    </button>
  );
}
