import type { Run } from "@/lib/api";
import { formatAge } from "@/lib/issues";
import { VerdictPill } from "@/components/badges";

// Run history for an issue: verdict + model + started_at only. Cost is
// deliberately omitted in Phase 1 — there is no `run-cost` element anywhere.
export function RunHistoryList({ runs }: { runs: Run[] }) {
  if (!runs.length) {
    return <p className="text-xs text-muted-foreground">No runs yet.</p>;
  }
  return (
    <ul className="space-y-1.5" data-testid="run-history">
      {runs.map((run) => (
        <li
          key={run.id}
          data-testid="run-row"
          className="flex items-center justify-between rounded-md border px-3 py-2 text-xs"
        >
          <div className="flex items-center gap-2">
            <VerdictPill verdict={run.verdict} />
            <span className="font-mono text-muted-foreground">
              {run.model ?? "—"}
            </span>
          </div>
          <span className="text-muted-foreground">{formatAge(run.started_at)}</span>
        </li>
      ))}
    </ul>
  );
}
