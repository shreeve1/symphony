"use client";

// F1 — bubble rendering for the issue chat flyout (#33 / spec §2–4).
//
// Splits `comments_md` on the §2.1 header grammar
//   `^### (agent|operator|patrol|system) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$`
// into per-role comment bubbles, renders each maximal run of un-headered
// prose as a collapsed legacy bucket (per §2.2), and interleaves two system
// run (start + terminal) into the timeline using the deterministic
// `(ts, kind_rank, id)` rule from §4 — comment < run_start < run_terminal.
//
// Variant B visual (§3): full-width blocks with role colors and a single
// avatar + role-name + timestamp header above each body. No left/right chat
// bubbles. System rows and legacy buckets are collapsed by default and
// expandable on click. Comments are rendered through the existing
// `Markdown` component so the same remark-gfm pipeline applies.

import { useState } from "react";

import type { Run } from "@/lib/api";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";

type Role = "agent" | "operator" | "patrol" | "system";

const HEADER_RE =
	/^### (agent|operator|patrol|system) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$/;

// Stable kind ranks for the §4 tie-break. On timestamp collision the bubble
// with the lower rank sorts first: comment < run_start < run_terminal.
// Legacy buckets sort last (highest rank) and use a nullish timestamp so they
// fall to the start of the timeline when no header precedes them, otherwise
// they slot in next to the most recent headered block above them.
const KIND_RANK = {
	comment: 0,
	run_start: 1,
	run_terminal: 2,
	legacy: 3,
} as const;

type Kind = keyof typeof KIND_RANK;

export type CommentBlock = {
	kind: "comment";
	id: string;
	role: Role;
	ts: string;
	body: string;
};

export type LegacyBlock = {
	kind: "legacy";
	id: string;
	body: string;
	// Inherited timestamp of the most recent header seen above (or null when
	// no header preceded the legacy run). Used purely for ordering; legacy
	// bubbles never render the timestamp itself.
	ts: string | null;
};

export type RunStartBlock = {
	kind: "run_start";
	id: string;
	ts: string;
	runId: number;
	agent: string | null;
	model: string | null;
	skill: string | null;
};

export type RunTerminalBlock = {
	kind: "run_terminal";
	id: string;
	ts: string;
	runId: number;
	state: string;
	verdict: string | null;
	summary: string | null;
	exitCode: number | null;
};

export type ChatBlock =
	| CommentBlock
	| LegacyBlock
	| RunStartBlock
	| RunTerminalBlock;

export function parseComments(
	source: string,
): Array<CommentBlock | LegacyBlock> {
	const lines = source.split("\n");
	const blocks: Array<CommentBlock | LegacyBlock> = [];
	let current: { role: Role; ts: string; id: string; body: string[] } | null =
		null;
	let legacyBody: string[] = [];
	let lastTs: string | null = null;

	const flushLegacy = () => {
		const text = legacyBody.join("\n").trim();
		legacyBody = [];
		if (!text) return;
		blocks.push({
			kind: "legacy",
			id: `legacy-${blocks.length}`,
			body: text,
			ts: lastTs,
		});
	};

	const flushComment = () => {
		if (!current) return;
		blocks.push({
			kind: "comment",
			id: current.id,
			role: current.role,
			ts: current.ts,
			body: current.body.join("\n").trim(),
		});
		current = null;
	};

	let commentIndex = 0;
	for (const line of lines) {
		const match = line.match(HEADER_RE);
		if (match) {
			flushLegacy();
			flushComment();
			current = {
				role: match[1] as Role,
				ts: match[2],
				id: `c-${commentIndex}`,
				body: [],
			};
			commentIndex++;
			lastTs = match[2];
		} else if (current) {
			current.body.push(line);
		} else {
			legacyBody.push(line);
		}
	}
	flushLegacy();
	flushComment();
	return blocks;
}

function runBubblesFor(run: Run): Array<RunStartBlock | RunTerminalBlock> {
	const out: Array<RunStartBlock | RunTerminalBlock> = [];
	if (run.started_at) {
		out.push({
			kind: "run_start",
			id: `run-start-${run.id}`,
			ts: run.started_at,
			runId: run.id,
			agent: run.agent,
			model: run.model,
			skill: run.skill_invoked,
		});
	}
	if (run.ended_at) {
		out.push({
			kind: "run_terminal",
			id: `run-terminal-${run.id}`,
			ts: run.ended_at,
			runId: run.id,
			state: run.state,
			verdict: run.verdict,
			summary: run.summary,
			exitCode: run.exit_code,
		});
	}
	return out;
}

function compareBlocks(a: ChatBlock, b: ChatBlock): number {
	// Null timestamps (legacy with no preceding header) sort first so the
	// pre-headered prose sits at the top of the thread.
	const aTs = "ts" in a ? (a.ts ?? "") : "";
	const bTs = "ts" in b ? (b.ts ?? "") : "";
	if (aTs !== bTs) {
		if (!aTs) return -1;
		if (!bTs) return 1;
		return aTs < bTs ? -1 : 1;
	}
	const rank = KIND_RANK[a.kind as Kind] - KIND_RANK[b.kind as Kind];
	if (rank !== 0) return rank;
	return a.id < b.id ? -1 : 1;
}

// Display formatting helpers.

function formatBubbleTs(ts: string): string {
	// ISO `YYYY-MM-DDTHH:MM:SSZ` → friendly `HH:MM:SS · YYYY-MM-DD UTC`. The
	// stamp stores ISO; the bubble displays a friendly localized time per §2.1.
	const date = new Date(ts);
	if (Number.isNaN(date.getTime())) return ts;
	const hh = String(date.getUTCHours()).padStart(2, "0");
	const mm = String(date.getUTCMinutes()).padStart(2, "0");
	const ss = String(date.getUTCSeconds()).padStart(2, "0");
	const yyyy = date.getUTCFullYear();
	const mo = String(date.getUTCMonth() + 1).padStart(2, "0");
	const dd = String(date.getUTCDate()).padStart(2, "0");
	return `${hh}:${mm}:${ss} · ${yyyy}-${mo}-${dd} UTC`;
}

const ROLE_LABEL: Record<Role, string> = {
	agent: "Agent",
	operator: "Operator",
	patrol: "Patrol",
	system: "System",
};

const ROLE_BADGE: Record<Role, string> = {
	agent: "bg-blue-100 text-blue-800 border-blue-200",
	operator: "bg-emerald-100 text-emerald-800 border-emerald-200",
	patrol: "bg-amber-100 text-amber-800 border-amber-200",
	system: "bg-slate-100 text-slate-700 border-slate-200",
};

const ROLE_BORDER: Record<Role, string> = {
	agent: "border-blue-300",
	operator: "border-emerald-300",
	patrol: "border-amber-300",
	system: "border-slate-300",
};

// Bubble atoms.

function CommentBubbleView({ block }: { block: CommentBlock }) {
	const label = ROLE_LABEL[block.role];
	return (
		<div
			data-testid={`bubble-${block.role}`}
			data-bubble-id={block.id}
			className={cn(
				"rounded-md border bg-background p-3",
				ROLE_BORDER[block.role],
			)}
		>
			<div className="mb-1 flex items-center gap-2">
				<span
					className={cn(
						"rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
						ROLE_BADGE[block.role],
					)}
				>
					{label}
				</span>
				<span
					className="text-xs text-muted-foreground"
					data-testid="bubble-ts"
				>
					{formatBubbleTs(block.ts)}
				</span>
			</div>
			{block.body && <Markdown source={block.body} />}
		</div>
	);
}

function LegacyBucket({ block }: { block: LegacyBlock }) {
	const [open, setOpen] = useState(false);
	const previewId = `legacy-${block.id}`;
	return (
		<div
			data-testid="legacy-bucket"
			data-legacy-id={block.id}
			className="rounded-md border border-dashed border-slate-300 bg-slate-50"
		>
			<button
				type="button"
				data-testid="legacy-toggle"
				aria-expanded={open}
				aria-controls={previewId}
				onClick={() => setOpen((value) => !value)}
				className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-muted-foreground hover:bg-slate-100"
			>
				<span aria-hidden className="font-mono">
					{open ? "▾" : "▸"}
				</span>
				<span>Legacy thread (older format)</span>
			</button>
			<div
				id={previewId}
				hidden={!open}
				className="border-t border-slate-200 p-3"
			>
				<Markdown source={block.body} />
			</div>
		</div>
	);
}

function RunStartView({ block }: { block: RunStartBlock }) {
	const parts = [
		block.agent ?? "agent",
		block.model ?? null,
		block.skill ?? null,
	].filter(Boolean);
	return (
		<div
			data-testid="run-start-bubble"
			data-run-id={block.runId}
			className="flex items-center gap-2 border-t border-dashed border-slate-200 px-1 py-1.5 text-xs text-muted-foreground"
		>
			<span aria-hidden className="font-mono">▶</span>
			<span>
				Run #{block.runId} started · {parts.join(" · ")}
			</span>
			<span className="ml-auto font-mono">
				{formatBubbleTs(block.ts)}
			</span>
		</div>
	);
}

function verdictLabel(block: RunTerminalBlock): string {
	if (block.verdict === "review" || block.verdict === "parked-for-review") {
		return "parked-for-review";
	}
	if (block.state === "succeeded") return "completed ✓";
	if (block.state === "blocked") return "blocked";
	if (block.state === "failed") {
		return `failed (exit ${block.exitCode ?? "?"})`;
	}
	if (block.verdict === "retry" || block.state === "retry") return "retry";
	return block.state;
}

function RunTerminalView({ block }: { block: RunTerminalBlock }) {
	const verdict = verdictLabel(block);
	const isParked = verdict === "parked-for-review";
	return (
		<div
			data-testid="run-terminal-bubble"
			data-run-id={block.runId}
			className={cn(
				"rounded-md border bg-slate-50 px-3 py-2 text-xs",
				isParked
					? "border-amber-300 bg-amber-50 text-amber-900"
					: "border-slate-200 text-slate-700",
			)}
		>
			<div className="flex items-center gap-2">
				<span aria-hidden className="font-mono">
					{isParked ? "★" : "■"}
				</span>
				<span
					data-testid="run-verdict"
					className="font-semibold uppercase tracking-wide"
				>
					Run #{block.runId} · {verdict}
				</span>
				<span className="ml-auto font-mono text-muted-foreground">
					{formatBubbleTs(block.ts)}
				</span>
			</div>
			{block.summary && (
				<p
					data-testid="run-summary"
					className="mt-1 text-muted-foreground"
				>
					{block.summary}
				</p>
			)}
		</div>
	);
}

// The system bubble rows per §1: machine markers (`### Symphony Retry Epoch`,
// `Symphony-Schedule:`, `**Symphony review passed:**`, etc.) get stamped with
// the `system` role by the write-side header work in #30. They render as a
// collapsed row, expandable on click.

function SystemRowView({ block }: { block: CommentBlock }) {
	const [open, setOpen] = useState(false);
	const previewId = `system-${block.id}`;
	return (
		<div
			data-testid="system-row"
			data-system-id={block.id}
			className="rounded-md border border-slate-200 bg-slate-50"
		>
			<button
				type="button"
				data-testid="system-toggle"
				aria-expanded={open}
				aria-controls={previewId}
				onClick={() => setOpen((value) => !value)}
				className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-slate-100"
			>
				<span aria-hidden className="font-mono">
					{open ? "▾" : "▸"}
				</span>
				<span className="font-mono">{formatBubbleTs(block.ts)}</span>
				<span>system</span>
			</button>
			<div
				id={previewId}
				hidden={!open}
				className="border-t border-slate-200 p-3"
			>
				{block.body && <Markdown source={block.body} />}
			</div>
		</div>
	);
}

function BubbleView({ block }: { block: ChatBlock }) {
	switch (block.kind) {
		case "comment":
			return block.role === "system" ? (
				<SystemRowView block={block} />
			) : (
				<CommentBubbleView block={block} />
			);
		case "legacy":
			return <LegacyBucket block={block} />;
		case "run_start":
			return <RunStartView block={block} />;
		case "run_terminal":
			return <RunTerminalView block={block} />;
	}
}

export function IssueChat({
	commentsMd,
	runs,
}: {
	commentsMd: string;
	runs: readonly Run[];
}) {
	const parsed = parseComments(commentsMd);
	const runBlocks = runs.flatMap(runBubblesFor);
	const merged: ChatBlock[] = [...parsed, ...runBlocks].sort(compareBlocks);
	if (merged.length === 0) {
		return (
			<p
				data-testid="chat-empty"
				className="rounded-md border border-dashed border-slate-300 p-3 text-xs text-muted-foreground"
			>
				No thread content yet.
			</p>
		);
	}
	return (
		<div data-testid="issue-chat" className="space-y-2">
			{merged.map((block) => (
				<BubbleView key={block.id} block={block} />
			))}
		</div>
	);
}