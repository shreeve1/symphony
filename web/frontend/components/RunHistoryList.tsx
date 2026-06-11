import type { Run } from "@/lib/api";
import { formatAge } from "@/lib/issues";
import { VerdictPill } from "@/components/badges";

// Run history for an issue: verdict + model + started_at only. Cost is
// deliberately omitted — there is no `run-cost` element anywhere.
export function RunHistoryList({
  runs,
  onSelectRun,
}: {
  runs: Run[];
  onSelectRun: (id: number) => void;
}) {
  if (!runs.length) {
    return <p className="text-xs text-muted-foreground">No runs yet.</p>;
  }
  return (
    <ul className="space-y-1.5" data-testid="run-history">
      {runs.map((run) => (
        <li key={run.id}>
          <button
            type="button"
            data-testid="run-row"
            onClick={() => onSelectRun(run.id)}
            className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-xs hover:bg-muted/60"
          >
            <div className="flex items-center gap-2">
              <VerdictPill verdict={run.verdict} />
              <span className="font-mono text-muted-foreground">
                {run.model ?? "—"}
              </span>
            </div>
            <span className="text-muted-foreground">{formatAge(run.started_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
