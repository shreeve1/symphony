"use client";

import { useEffect, useMemo, useRef } from "react";

import { useTailEvents } from "@/components/QueryProvider";

/** Format a single JSONL line for human-readable display. Tries to pretty-print the JSON. */
function formatSessionTailLine(raw: string): string {
	try {
		const parsed = JSON.parse(raw);
		return JSON.stringify(parsed, null, 2);
	} catch {
		return raw;
	}
}

export function SessionTailPanel({ issueId }: { issueId: number | null }) {
	const allTailEvents = useTailEvents();
	const scrollRef = useRef<HTMLDivElement | null>(null);
	const lines = useMemo(() => {
		if (issueId == null) return [];
		return allTailEvents
			.filter((event) => event.issue_id === issueId)
			.flatMap((event) => event.lines);
	}, [allTailEvents, issueId]);

	// Auto-scroll to bottom when new lines arrive.
	useEffect(() => {
		const el = scrollRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [lines]);

	if (issueId == null) return null;

	return (
		<div data-testid="session-tail-panel" className="space-y-2">
			{lines.length === 0 ? (
				<p
					data-testid="session-tail-empty"
					className="text-xs text-muted-foreground"
				>
					No active session — tail data appears here when the agent runs.
				</p>
			) : (
				<div
					ref={scrollRef}
					data-testid="session-tail-log"
					className="max-h-[60vh] overflow-y-auto rounded-md border bg-muted/30 p-3 font-mono text-xs"
				>
					{lines.map((line, i) => (
						<pre
							key={i}
							data-testid="session-tail-line"
							className="whitespace-pre-wrap break-all"
						>
							{formatSessionTailLine(line)}
						</pre>
					))}
				</div>
			)}
		</div>
	);
}
