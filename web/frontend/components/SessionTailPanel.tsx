"use client";

// F3: Live-tail consumer + catch-up flow (issue #35).
//
// Owns the in-memory transcript for one (issue_id, run_id) pair, merging:
//   1. The REST catch-up snapshot at GET /api/runs/{id}/tail (on mount and
//      on WS reconnect).
//   2. The streamed `run.tail` WS deltas from QueryProvider, deduped against
//      the catch-up cursor so a line already in the snapshot is not appended
//      a second time.
//
// Renders a chat: tool pills (Bash/Read/Write/Edit/Glob/Grep/Task/TodoWrite),
// per-pill row cap with "show more", 3+ consecutive pill auto-cluster, an
// activity-status row above the chat (thinking cyan pulse / tool_executing
// purple spin, aria-live=polite), and the marked → DOMPurify markdown
// pipeline. Completed runs collapse to a terminal bubble + summary only.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useTailEvents } from "@/components/QueryProvider";
import { fetchIssueRuns, fetchRunTail, tailClusterThreshold, type Run, type RunTailSnapshot } from "@/lib/api";
import { isActiveRunState } from "@/lib/polling";
import { renderMarkdownSafe, highlightBubble } from "@/lib/markdown";

// ── Types ─────────────────────────────────────────────────────────

type ToolName =
	| "Bash"
	| "Read"
	| "Write"
	| "Edit"
	| "Glob"
	| "Grep"
	| "Task"
	| "TodoWrite";

// Per the §6 extensibility map. Unknown names fall back to "·" so a future
// tool that pi learns first still renders a pill.
const TOOL_ICON: Record<ToolName, string> = {
	Bash: "$",
	Read: "R",
	Write: "W",
	Edit: "E",
	Glob: "G",
	Grep: "?",
	Task: "T",
	TodoWrite: "✓",
};
function toolIcon(name: string): string {
	return TOOL_ICON[name as ToolName] ?? "·";
}

// Pi/Claude JSONL event vocabulary — the un-pinned piece of the spec. We map
// the observed shapes we know about (assistant text, tool_use, tool_result,
// assistant text deltas) into a uniform pill/delta model. Unknown shapes
// degrade to a raw "json" pill so nothing is silently dropped.
type ParsedLine =
	| { kind: "text"; text: string }
	| { kind: "tool"; tool: string; input?: unknown; output?: unknown; status: "running" | "ok" | "error" }
	| { kind: "status"; label: string }
	| { kind: "json"; raw: string };

function parseLine(raw: string): ParsedLine {
	try {
		const value = JSON.parse(raw) as Record<string, unknown>;
		const type = typeof value.type === "string" ? value.type : "";
		// Pi assistant text block (text part of a multi-part assistant message)
		if (type === "text" || (type === "assistant" && typeof value.text === "string")) {
			return { kind: "text", text: String(value.text ?? "") };
		}
		// Pi/Claude streaming text delta
		if (type === "text_delta" || type === "content_block_delta") {
			const delta = value.delta ?? value.text;
			if (typeof delta === "string") return { kind: "text", text: delta };
		}
		// Tool call (pi style: tool_call; claude style: tool_use)
		if (type === "tool_use" || type === "tool_call") {
			const tool = String(value.name ?? value.tool ?? "tool");
			return {
				kind: "tool",
				tool,
				input: value.input ?? value.arguments,
				status: "running",
			};
		}
		// Tool result (matches the tool_use/tool_call above by id)
		if (type === "tool_result") {
			const isError = value.is_error === true;
			return {
				kind: "tool",
				tool: String(value.name ?? value.tool ?? "tool"),
				output: value.content ?? value.output,
				status: isError ? "error" : "ok",
			};
		}
		// Status / activity events surface in the activity-status row.
		if (type === "thinking") return { kind: "status", label: "thinking" };
		if (type === "tool_executing")
			return {
				kind: "status",
				label: "tool_executing",
			};
		if (type === "agent_end" || type === "result")
			return { kind: "status", label: "turn_finished" };
	} catch {
		// Non-JSON line — render as a raw pill so the operator sees it.
	}
	return { kind: "json", raw };
}

interface IndexedLine {
	cursor: number;
	parsed: ParsedLine;
}

interface DisplayBlock {
	kind: "text" | "tool" | "cluster" | "status" | "raw";
	text?: string;
	tools?: IndexedTool[];
	cluster?: { total: number; done: number; byTool: Record<string, number> };
	raw?: string;
	tool?: string;
}

interface IndexedTool {
	tool: string;
	status: "running" | "ok" | "error";
	input?: unknown;
	output?: unknown;
}

// ── Helpers ────────────────────────────────────────────────────────

const ROW_CAP = 200;
const CHAR_CAP = 200;

function truncate(text: string, lineLimit = ROW_CAP, charLimit = CHAR_CAP): {
	body: string;
	truncated: boolean;
	droppedLines: number;
} {
	const lines = text.split("\n");
	const kept = lines.slice(0, lineLimit).map((l) =>
		l.length > charLimit ? `${l.slice(0, charLimit)}…` : l,
	);
	const truncated = lines.length > lineLimit;
	return {
		body: kept.join("\n"),
		truncated,
		droppedLines: Math.max(0, lines.length - lineLimit),
	};
}

function summarizeToolInput(tool: string, input: unknown): string {
	if (input == null) return tool;
	if (typeof input === "string") return input.split("\n")[0].slice(0, 80) || tool;
	if (typeof input === "object") {
		const obj = input as Record<string, unknown>;
		if (tool === "Bash" && typeof obj.command === "string")
			return obj.command.split("\n")[0].slice(0, 80);
		if (tool === "Read" && typeof obj.path === "string") return obj.path;
		if (tool === "Write" && typeof obj.path === "string") return obj.path;
		if (tool === "Edit" && typeof obj.path === "string") return obj.path;
		if (tool === "Glob" && typeof obj.pattern === "string") return obj.pattern;
		if (tool === "Grep" && typeof obj.pattern === "string") return obj.pattern;
	}
	return tool;
}

function asString(value: unknown): string {
	if (value == null) return "";
	if (typeof value === "string") return value;
	if (Array.isArray(value)) return value.map(asString).join("");
	return JSON.stringify(value);
}

// ── Component ──────────────────────────────────────────────────────

interface Props {
	issueId: number;
}

export function SessionTailPanel({ issueId }: Props) {
	const allTailEvents = useTailEvents();
	const runsQuery = useQuery({
		queryKey: ["runs", issueId],
		queryFn: () => fetchIssueRuns(issueId),
		enabled: issueId != null,
	});
	const runs = runsQuery.data;
	const scrollRef = useRef<HTMLDivElement | null>(null);
	const [snapshot, setSnapshot] = useState<RunTailSnapshot | null>(null);
	const [indexed, setIndexed] = useState<IndexedLine[]>([]);
	const [expandedPills, setExpandedPills] = useState<Set<number>>(new Set());
	const [sourceId, setSourceId] = useState<string | null>(null);
	const [activity, setActivity] = useState<"thinking" | "tool_executing" | "idle">("idle");
	const lastNotifiedRunRef = useRef<number | null>(null);

	const activeRun = useMemo<Run | null>(() => {
		if (!runs) return null;
		return runs.find((r) => isActiveRunState(r.state)) ?? null;
	}, [runs]);

	// The latest finished run is what the "completed runs collapse" path reads
	// from: terminal bubble + summary, no transcript browse.
	const lastFinishedRun = useMemo<Run | null>(() => {
		if (!runs || runs.length === 0) return null;
		const finished = runs.filter((r) => !isActiveRunState(r.state));
		return finished[0] ?? null;
	}, [runs]);

	// Filter tail events to this issue and the active run. The legacy
	// useTailEvents() shape is preserved (issue_id, lines), so we accept
	// either the old or the enriched (run_id, source_id, line_cursors) shape.
	const relevantEvents = useMemo(() => {
		return allTailEvents.filter(
			(e) => e.issue_id === issueId && (activeRun == null || e.run_id == null || e.run_id === activeRun.id),
		);
	}, [allTailEvents, issueId, activeRun]);

	// ── Catch-up: GET /api/runs/{id}/tail on mount + when run becomes active
	//    and on source_id rotation. The `trigger` state lives below to force
	//    a refetch on rotation (criterion 9).
	const [catchupTrigger, setCatchupTrigger] = useState(0);
	const activeRunId = activeRun?.id ?? null;
	useEffect(() => {
		if (activeRunId == null) {
			setSnapshot(null);
			setIndexed([]);
			setSourceId(null);
			return;
		}
		let cancelled = false;
		const fetchOnce = async () => {
			try {
				const snap = await fetchRunTail(activeRunId);
				if (cancelled) return;
				setSnapshot(snap);
				setSourceId(snap.source_id || null);
				const seeded: IndexedLine[] = snap.lines.map((line, i) => ({
					cursor: snap.line_cursors[i] ?? snap.cursor,
					parsed: parseLine(line),
				}));
				setIndexed(seeded);
			} catch {
				// fetchRunTail swallows 404; any other failure is silent so the
				// flyout open animation is not blocked.
			}
		};
		fetchOnce();
		return () => {
			cancelled = true;
		};
	}, [activeRunId, catchupTrigger]);

	// ── Source-id rotation: if a future WS event carries a new source_id
	//    (inode change), reset and refetch (criterion 9).
	const lastSeenSourceRef = useRef<string | null>(null);
	const hasObservedSourceRef = useRef(false);
	useEffect(() => {
		let rotated = false;
		for (const event of relevantEvents) {
			const ev = event as { source_id?: string; run_id?: number | null };
			if (!ev.source_id) continue;
			if (
				hasObservedSourceRef.current &&
				ev.source_id !== lastSeenSourceRef.current
			) {
				rotated = true;
			}
			lastSeenSourceRef.current = ev.source_id;
			hasObservedSourceRef.current = true;
		}
		if (rotated) setCatchupTrigger((n) => n + 1);
	}, [relevantEvents]);

	// ── Merge live WS deltas into the indexed buffer (criterion 1).
	//    Drop any line whose cursor is <= snapshot.cursor; append the rest.
	useEffect(() => {
		if (relevantEvents.length === 0) return;
		setIndexed((prev) => {
			const cursorFloor = snapshot?.cursor ?? 0;
			const have = new Set(prev.map((l) => l.cursor));
			const additions: IndexedLine[] = [];
			let lastActivity: "thinking" | "tool_executing" | "idle" = activityRef.current;
			let turnFinished = false;
			for (const event of relevantEvents) {
				const ev = event as {
					lines: string[];
					line_cursors?: number[];
					cursor?: number;
				};
				const cursors = ev.line_cursors ?? [];
				for (let i = 0; i < ev.lines.length; i += 1) {
					const cursor = cursors[i] ?? ev.cursor ?? 0;
					if (cursor <= cursorFloor) continue;
					if (have.has(cursor)) continue;
					const parsed = parseLine(ev.lines[i]);
					additions.push({ cursor, parsed });
					if (parsed.kind === "status") {
						if (parsed.label === "thinking") lastActivity = "thinking";
						if (parsed.label === "tool_executing") lastActivity = "tool_executing";
						if (parsed.label === "turn_finished") turnFinished = true;
					}
				}
			}
			if (
				additions.length === 0 &&
				!turnFinished &&
				lastActivity === activityRef.current
			)
				return prev;
			activityRef.current = lastActivity;
			setActivity(lastActivity);
			if (turnFinished) {
				setActivity("idle");
				activityRef.current = "idle";
				fireTurnFinishedNotification(activeRunId, lastNotifiedRunRef);
			}
			return [...prev, ...additions];
		});
	}, [relevantEvents, snapshot?.cursor, activeRunId]);

	// Auto-scroll to bottom on new content (criterion 6 / general UX).
	useEffect(() => {
		const el = scrollRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [indexed.length]);

	// ── Build display blocks: cluster 3+ consecutive tool pills.
	const blocks = useMemo<DisplayBlock[]>(() => {
		const out: DisplayBlock[] = [];
		const clusterThreshold = tailClusterThreshold();
		let i = 0;
		while (i < indexed.length) {
			const line = indexed[i];
			if (line.parsed.kind === "text") {
				out.push({ kind: "text", text: line.parsed.text });
				i += 1;
				continue;
			}
			if (line.parsed.kind === "tool") {
				// Walk forward while we have consecutive tool pills.
				const run: IndexedTool[] = [];
				while (i < indexed.length && indexed[i].parsed.kind === "tool") {
					const p = indexed[i].parsed as Extract<ParsedLine, { kind: "tool" }>;
					run.push({
						tool: p.tool,
						status: p.status,
						input: p.input,
						output: p.output,
					});
					i += 1;
				}
				if (run.length >= clusterThreshold) {
					const byTool: Record<string, number> = {};
					let done = 0;
					for (const t of run) {
						byTool[t.tool] = (byTool[t.tool] ?? 0) + 1;
						if (t.status === "ok" || t.status === "error") done += 1;
					}
					out.push({ kind: "cluster", tools: run, cluster: { total: run.length, done, byTool } });
				} else {
					for (const t of run) out.push({ kind: "tool", tool: t.tool, tools: [t] });
				}
				continue;
			}
			if (line.parsed.kind === "status") {
				out.push({ kind: "status", text: line.parsed.label });
				i += 1;
				continue;
			}
			out.push({ kind: "raw", raw: line.parsed.raw });
			i += 1;
		}
		return out;
	}, [indexed]);

	// Render the activity-status row above the chat. aria-live=polite is on
	// the wrapper so screen readers announce the transition without
	// interrupting.
	const activityRow = (() => {
		if (activity === "thinking") {
			return (
				<div
					data-testid="activity-status"
					aria-live="polite"
					className="flex items-center gap-2 px-2 py-1 text-xs text-cyan-700"
				>
					<span
						data-testid="activity-pulse"
						aria-hidden
						className="motion-safe:animate-pulse inline-block h-2 w-2 rounded-full bg-cyan-500"
					/>
					<span>thinking…</span>
				</div>
			);
		}
		if (activity === "tool_executing") {
			return (
				<div
					data-testid="activity-status"
					aria-live="polite"
					className="flex items-center gap-2 px-2 py-1 text-xs text-purple-700"
				>
					<span
						data-testid="activity-spin"
						aria-hidden
						className="motion-safe:animate-spin inline-block h-2 w-2 rounded-full border-2 border-purple-500 border-t-transparent"
					/>
					<span>tool_executing…</span>
				</div>
			);
		}
		return null;
	})();

	if (!activeRun) {
		// Completed runs (or no runs at all): terminal bubble + summary only.
		// The spec's i-a says no transcript browse for completed runs.
		if (lastFinishedRun) {
			const summary = lastFinishedRun.summary ?? "(no summary)";
			return (
				<div data-testid="session-tail-panel" className="space-y-2">
					<div
						data-testid="session-tail-terminal"
						className="rounded-md border bg-muted/30 p-3 text-sm"
					>
						<div className="mb-1 text-xs text-muted-foreground">
							Run #{lastFinishedRun.id} · {lastFinishedRun.state}
						</div>
						<div data-testid="session-tail-summary">{summary}</div>
					</div>
				</div>
			);
		}
		return (
			<div data-testid="session-tail-panel" className="space-y-2">
				<p
					data-testid="session-tail-empty"
					className="text-xs text-muted-foreground"
				>
					No active session — tail data appears here when the agent runs.
				</p>
			</div>
		);
	}

	const togglePill = (idx: number) =>
		setExpandedPills((prev) => {
			const next = new Set(prev);
			if (next.has(idx)) next.delete(idx);
			else next.add(idx);
			return next;
		});

	return (
		<div data-testid="session-tail-panel" className="space-y-2">
			{activityRow}
			{indexed.length === 0 ? (
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
					className="max-h-[60vh] space-y-2 overflow-y-auto rounded-md border bg-muted/30 p-3 font-mono text-xs"
				>
					{blocks.map((block, idx) => {
						if (block.kind === "text" && block.text) {
							const html = renderMarkdownSafe(block.text);
							// pi-lens-ignore: marked -> DOMPurify pipeline
							return (
								<MarkdownBubble key={idx} html={html} />
							);
						}
						if (block.kind === "cluster" && block.tools && block.cluster) {
							return (
								<div
									key={idx}
									data-testid="session-tail-cluster"
									className="rounded-md border bg-background/60 p-2"
								>
									<div className="text-xs text-muted-foreground">
										{block.cluster.total} tool calls (
										{Object.entries(block.cluster.byTool)
											.map(([name, count]) => `${count} ${name}`)
											.join(", ")}
										) — {block.cluster.done}/{block.cluster.total} done
									</div>
								</div>
							);
						}
						if (block.kind === "tool" && block.tools) {
							return block.tools.map((t, j) => {
								const flatIdx = idx * 100 + j;
								const expanded = expandedPills.has(flatIdx);
								const bodyRaw = asString(t.output);
								const { body, truncated, droppedLines } = truncate(bodyRaw);
								return (
									<div
										key={flatIdx}
										data-testid="session-tail-pill"
										data-tool={t.tool}
										className="rounded-md border bg-background/60 p-2"
									>
										<button
											type="button"
											data-testid="session-tail-pill-toggle"
											onClick={() => togglePill(flatIdx)}
											className="flex w-full items-center gap-2 text-left"
										>
											<span
												aria-hidden
												className="inline-flex h-5 w-5 items-center justify-center rounded border bg-muted text-[10px] font-bold"
											>
												{toolIcon(t.tool)}
											</span>
											<span className="font-semibold">{t.tool}</span>
											<span className="truncate text-muted-foreground">
												{summarizeToolInput(t.tool, t.input)}
											</span>
											<span
												data-testid="session-tail-pill-status"
												className="ml-auto text-xs"
											>
												{t.status === "running"
													? "⋯"
													: t.status === "ok"
														? "✓"
														: "✗"}
											</span>
										</button>
										{(expanded || body) && (
											<pre
												data-testid="session-tail-pill-output"
												className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words border-t pt-2 text-[11px]"
											>
												{body || (t.input ? asString(t.input) : "")}
											</pre>
										)}
										{truncated && (
											<button
												type="button"
												data-testid="session-tail-show-more"
												onClick={() => togglePill(flatIdx)}
												className="mt-1 text-[11px] text-blue-600 hover:underline"
											>
												{expanded ? "show less" : `show more (+${droppedLines} lines)`}
											</button>
										)}
									</div>
								);
							});
						}
						if (block.kind === "raw" && block.raw) {
							// Legacy fallback so a non-JSONL line still shows up
							// under the same session-tail-line testid the e2e
							// suite uses.
							return (
								<pre
									key={idx}
									data-testid="session-tail-line"
									className="whitespace-pre-wrap break-all"
								>
									{block.raw}
								</pre>
							);
						}
						if (block.kind === "status" && block.text) {
							return (
								<div
									key={idx}
									data-testid="session-tail-status"
									className="text-[11px] text-muted-foreground"
								>
									{block.text}
								</div>
							);
						}
						return null;
					})}
				</div>
			)}
		</div>
	);
}

// ── Web Notification helper (criterion 11) ─────────────────────────
//
// Only fires when document.hidden is true (operator backgrounded the tab) and
// only on turn_finish. The browser will silently no-op the permission
// request if the user previously denied; we never block the chat on it.
const activityRef: { current: "thinking" | "tool_executing" | "idle" } = {
	current: "idle",
};

function fireTurnFinishedNotification(
	runId: number | null,
	lastNotifiedRef: { current: number | null },
) {
	if (runId == null || lastNotifiedRef.current === runId) return;
	if (typeof document === "undefined" || !document.hidden) return;
	if (typeof window === "undefined" || !("Notification" in window)) return;
	lastNotifiedRef.current = runId;
	try {
		if (Notification.permission === "granted") {
			new Notification("Podium", {
				body: "Agent turn finished",
				tag: `podium-turn-${runId}`,
			});
		} else if (Notification.permission !== "denied") {
			Notification.requestPermission().then((perm) => {
				if (perm === "granted") {
					new Notification("Podium", { body: "Agent turn finished" });
				}
			});
		}
	} catch {
		// Some browsers throw on Notification construction; we just skip.
	}
}

// MarkdownBubble renders one chat bubble's worth of pre-sanitized HTML and
// applies Prism syntax-highlighting to its <pre><code> children in a
// useLayoutEffect so the next paint already has the tokens. The
// dangerouslySetInnerHTML call is the single innerHTML-set call in this
// module and is the one annotated with the `pi-lens-ignore` comment for
// the future DOMPurify-tightening audit.
function MarkdownBubble({ html }: { html: string }) {
	const ref = useRef<HTMLDivElement | null>(null);
	useLayoutEffect(() => {
		if (ref.current) highlightBubble(ref.current);
	}, [html]);
	return (
		<div
			ref={ref}
			data-testid="session-tail-bubble"
			className="session-tail-bubble rounded-md border bg-background p-2"
			// pi-lens-ignore: marked -> DOMPurify pipeline
			// eslint-disable-next-line react/no-danger
			dangerouslySetInnerHTML={{ __html: html }}
		/>
	);
}
