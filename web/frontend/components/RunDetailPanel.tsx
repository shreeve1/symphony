import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchRun, fetchRunLog, type RunDetail } from "@/lib/api";
import { runDetailRefetchIntervalMs } from "@/lib/polling";
import { formatRunDuration, isLiveElapsedRun } from "@/lib/run-duration";

function formatValue(value: string | number | null | undefined) {
	return value == null || value === "" ? "—" : String(value);
}

function useLiveNow(run: RunDetail | undefined) {
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		if (!isLiveElapsedRun(run)) return;
		setNow(Date.now());
		const timer = window.setInterval(() => setNow(Date.now()), 1_000);
		return () => window.clearInterval(timer);
	}, [run?.id, run?.state, run?.started_at, run?.ended_at]);
	return now;
}

export function RunDetailPanel({
	runId,
	onClose,
}: {
	runId: number;
	onClose: () => void;
}) {
	const run = useQuery({
		queryKey: ["run", runId],
		queryFn: () => fetchRun(runId),
		refetchInterval: (query) => runDetailRefetchIntervalMs(query.state.data),
	});
	const log = useQuery({
		queryKey: ["run-log", runId],
		queryFn: () => fetchRunLog(runId),
		refetchInterval: () => runDetailRefetchIntervalMs(run.data),
	});
	const logRef = useRef<HTMLPreElement | null>(null);
	const now = useLiveNow(run.data);

	useEffect(() => {
		const node = logRef.current;
		if (node) node.scrollTop = node.scrollHeight;
	}, [log.data]);

	const fields: [string, string][] = [
		["agent", formatValue(run.data?.agent)],
		["provider", formatValue(run.data?.provider)],
		["model", formatValue(run.data?.model)],
		["verdict", formatValue(run.data?.verdict)],
		[
			"tokens",
			`${formatValue(run.data?.input_tokens)} in / ${formatValue(run.data?.output_tokens)} out`,
		],
		["started", formatValue(run.data?.started_at)],
		["ended", formatValue(run.data?.ended_at)],
		["duration", formatRunDuration(run.data, now)],
		["branch", formatValue(run.data?.branch_name)],
	];

	return (
		<aside
			data-testid="run-detail-flyout"
			className="absolute inset-y-0 right-0 z-20 flex w-full flex-col border-l bg-background shadow-xl"
		>
			<div className="flex items-center justify-between border-b px-6 py-4">
				<div>
					<p className="text-xs uppercase tracking-wide text-muted-foreground">
						Run detail
					</p>
					<h3 className="text-lg font-semibold">Run #{runId}</h3>
				</div>
				<button
					type="button"
					data-testid="close-run-detail"
					onClick={onClose}
					className="rounded-md border px-3 py-1.5 text-sm"
				>
					Back
				</button>
			</div>

			<div className="flex-1 space-y-4 overflow-y-auto p-6">
				{run.isError ? (
					<p className="text-sm text-red-500">Failed to load this run.</p>
				) : (
					<div
						data-testid="run-metadata-grid"
						className="grid grid-cols-2 gap-2 text-xs"
					>
						{fields.map(([label, value]) => (
							<div
								key={label}
								data-testid={`run-field-${label}`}
								className="rounded-md border p-2"
							>
								<div className="uppercase tracking-wide text-muted-foreground">
									{label}
								</div>
								<div className="mt-1 break-words font-medium">{value}</div>
							</div>
						))}
					</div>
				)}

				<div className="space-y-2">
					<div className="flex items-center justify-between">
						<h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
							Log
						</h4>
						<button
							type="button"
							data-testid="reload-run-log"
							onClick={() => log.refetch()}
							className="rounded-md border px-2 py-1 text-xs"
						>
							Reload
						</button>
					</div>
					<pre
						ref={logRef}
						data-testid="run-log-pane"
						className="h-80 overflow-y-auto rounded-md border bg-muted/30 p-3 text-xs"
					>
						{log.data ? log.data : "No log on disk for this run."}
					</pre>
				</div>
			</div>
		</aside>
	);
}
