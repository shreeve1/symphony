"use client";

import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight } from "lucide-react";

import { fetchBindingIssues, fetchBindings, type Issue } from "@/lib/api";
import { STATES } from "@/lib/issues";
import { cn } from "@/lib/utils";

type StateKey = (typeof STATES)[number]["key"];

interface BindingSummary {
	name: string;
	displayName: string;
	color: string;
	counts: Record<StateKey, number>;
	total: number;
	lastEventAt: string | null;
}

function countByState(issues: Issue[]): Record<StateKey, number> {
	const counts = {} as Record<StateKey, number>;
	for (const s of STATES) counts[s.key] = 0;
	for (const issue of issues) {
		const key = issue.state as StateKey;
		if (key in counts) counts[key] += 1;
	}
	return counts;
}

function formatAge(iso: string | null): string {
	if (!iso) return "—";
	const secs = Math.max(
		0,
		Math.floor((Date.now() - new Date(iso).getTime()) / 1000),
	);
	if (secs < 60) return `${secs}s ago`;
	const mins = Math.floor(secs / 60);
	if (mins < 60) return `${mins}m ago`;
	const hours = Math.floor(mins / 60);
	if (hours < 24) return `${hours}h ago`;
	return `${Math.floor(hours / 24)}d ago`;
}

function lastActivity(issues: Issue[]): string | null {
	const timestamps = issues
		.map((i) => i.last_event_at)
		.filter((t): t is string => t != null);
	if (!timestamps.length) return null;
	return timestamps.sort().reverse()[0] ?? null;
}

function isAttention(issue: Issue): boolean {
	return (
		issue.state === "blocked" ||
		issue.latest_verdict === "blocked" ||
		issue.latest_run_state === "failed"
	);
}

function StateBadge({
	label,
	count,
	dot,
}: {
	label: string;
	count: number;
	dot: string;
}) {
	return (
		<span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-2 py-0.5 text-xs">
			<span className={cn("size-1.5 rounded-full", dot)} />
			<span className="text-muted-foreground">{label}</span>
			<span className="font-medium">{count}</span>
		</span>
	);
}

function BindingCard({ summary }: { summary: BindingSummary }) {
	return (
		<Link
			href={`/${summary.name}`}
			data-testid={`dashboard-binding-${summary.name}`}
			className="rounded-lg border bg-card p-4 shadow-sm transition hover:shadow-md"
		>
			<div className="mb-3 flex items-center gap-2">
				<span
					aria-hidden
					className="size-3 shrink-0 rounded-full"
					style={{ backgroundColor: summary.color }}
				/>
				<h3 className="font-semibold">{summary.displayName}</h3>
				<span className="ml-auto text-[11px] text-muted-foreground">
					{formatAge(summary.lastEventAt)}
				</span>
			</div>
			<div className="flex flex-wrap gap-1.5">
				{STATES.map((s) => (
					<StateBadge
						key={s.key}
						label={s.label}
						count={summary.counts[s.key]}
						dot={s.dot}
					/>
				))}
			</div>
		</Link>
	);
}

function AttentionRow({ issue, binding }: { issue: Issue; binding: string }) {
	return (
		<Link
			key={issue.id}
			href={`/${binding}?issue=${issue.id}`}
			data-testid="attention-row"
			className="flex items-center gap-3 rounded-md border bg-card px-3 py-2 text-sm transition hover:shadow-sm"
		>
			<AlertCircle className="size-4 shrink-0 text-red-500" />
			<span className="flex-1 truncate font-medium">{issue.title}</span>
			<span className="shrink-0 text-xs text-muted-foreground">
				{issue.state === "blocked"
					? "blocked"
					: issue.latest_verdict === "blocked"
						? "verdict: blocked"
						: "run failed"}
			</span>
			<ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
		</Link>
	);
}

export default function DashboardPage() {
	const bindingsQuery = useQuery({
		queryKey: ["bindings"],
		queryFn: fetchBindings,
	});

	const activeBindings = (bindingsQuery.data ?? []).filter((b) => !b.archived);

	const issuesQueries = useQueries({
		queries: activeBindings.map((b) => ({
			queryKey: ["issues", b.name],
			queryFn: () => fetchBindingIssues(b.name),
			enabled: bindingsQuery.isSuccess,
		})),
	});

	const isLoading =
		bindingsQuery.isLoading || issuesQueries.some((q) => q.isLoading);
	const isError = bindingsQuery.isError || issuesQueries.some((q) => q.isError);

	const summaries: BindingSummary[] = activeBindings.map((b, i) => {
		const issues = issuesQueries[i]?.data ?? [];
		return {
			name: b.name,
			displayName: b.display_name,
			color: b.color,
			counts: countByState(issues),
			total: issues.length,
			lastEventAt: lastActivity(issues),
		};
	});

	// Global roll-up
	const globalCounts: Record<StateKey, number> = (() => {
		const c = {} as Record<StateKey, number>;
		for (const s of STATES) c[s.key] = 0;
		for (const s of summaries) {
			for (const key of STATES.map((x) => x.key)) c[key] += s.counts[key];
		}
		return c;
	})();
	const globalTotal = summaries.reduce((a, s) => a + s.total, 0);

	// Attention list: blocked or verdict=blocked or run=failed across all bindings
	const attentionItems: { issue: Issue; binding: string }[] = [];
	for (let i = 0; i < activeBindings.length; i++) {
		const issues = issuesQueries[i]?.data ?? [];
		for (const issue of issues) {
			if (isAttention(issue)) {
				attentionItems.push({ issue, binding: activeBindings[i].name });
			}
		}
	}

	return (
		<div className="mx-auto max-w-4xl space-y-8">
			<div>
				<h2 className="text-2xl font-semibold tracking-tight">Dashboard</h2>
				<p className="text-sm text-muted-foreground">Cross-binding overview</p>
			</div>

			{isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
			{isError && <p className="text-sm text-red-500">Failed to load data</p>}

			{!isLoading && !isError && (
				<>
					{/* Global roll-up */}
					<div data-testid="dashboard-global-rollup" className="space-y-2">
						<h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
							All bindings
						</h3>
						<div className="rounded-lg border bg-card p-4 shadow-sm">
							<div className="mb-2 text-2xl font-bold">
								{globalTotal} issues
							</div>
							<div className="flex flex-wrap gap-1.5">
								{STATES.map((s) => (
									<StateBadge
										key={s.key}
										label={s.label}
										count={globalCounts[s.key]}
										dot={s.dot}
									/>
								))}
							</div>
						</div>
					</div>

					{/* Attention list */}
					<div data-testid="dashboard-attention" className="space-y-2">
						<h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
							Needs attention
						</h3>
						{attentionItems.length === 0 ? (
							<p
								data-testid="attention-empty"
								className="text-sm text-muted-foreground"
							>
								Nothing needs attention
							</p>
						) : (
							<div className="space-y-1.5">
								{attentionItems.map(({ issue, binding }) => (
									<AttentionRow
										key={issue.id}
										issue={issue}
										binding={binding}
									/>
								))}
							</div>
						)}
					</div>

					{/* Per-binding cards */}
					<div
						data-testid="dashboard-binding-cards"
						className="grid gap-4 sm:grid-cols-2"
					>
						{summaries.map((s) => (
							<BindingCard key={s.name} summary={s} />
						))}
					</div>
				</>
			)}
		</div>
	);
}
