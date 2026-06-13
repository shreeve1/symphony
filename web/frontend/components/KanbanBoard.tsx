"use client";

import { useCallback, useEffect, useState } from "react";
// dnd-kit is wired in here as a placeholder for drag-and-drop in a later slice
// (#012c installs it; no drag handlers are attached yet).
import { DndContext } from "@dnd-kit/core";
import { useParams, useRouter } from "next/navigation";

import type { Issue } from "@/lib/api";
import { STATES } from "@/lib/issues";
import { cn } from "@/lib/utils";
import { IssueCard } from "@/components/IssueCard";
import { IssueFlyout } from "@/components/IssueFlyout";

export function KanbanBoard({
	issues,
	initialIssueId,
}: {
	issues: Issue[];
	initialIssueId?: number | null;
}) {
	const router = useRouter();
	const { binding } = useParams<{ binding: string }>();
	const [selected, setSelected] = useState<number | null>(
		initialIssueId ?? null,
	);

	// Sync the open flyout when the ?issue= deep link changes without a remount
	// (e.g. clicking another inbox item within the same binding). The useState
	// initializer only runs on mount, so same-binding navigations are missed.
	useEffect(() => {
		if (initialIssueId != null) {
			setSelected(initialIssueId);
		}
	}, [initialIssueId]);

	// Per-binding collapse state persisted in localStorage.
	const storageKey = `podium.collapsed.${binding ?? ""}`;
	const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

	useEffect(() => {
		if (!binding) return;
		try {
			const raw = localStorage.getItem(storageKey);
			if (!raw) {
				// Default: archived column collapsed; others expanded.
				setCollapsed(new Set(["archived"]));
				return;
			}
			const parsed = JSON.parse(raw);
			setCollapsed(Array.isArray(parsed) ? new Set(parsed) : new Set());
		} catch {
			setCollapsed(new Set());
		}
	}, [binding, storageKey]);

	const toggleCollapse = useCallback(
		(key: string) => {
			setCollapsed((prev) => {
				const next = new Set(prev);
				if (next.has(key)) {
					next.delete(key);
				} else {
					next.add(key);
				}
				try {
					localStorage.setItem(storageKey, JSON.stringify([...next]));
				} catch {
					// Storage full or unavailable — ignore
				}
				return next;
			});
		},
		[storageKey],
	);

	const closeFlyout = useCallback(() => {
		setSelected(null);
		if (binding) {
			router.replace(`/${binding}`);
		}
	}, [binding, router]);

	return (
		<DndContext>
			<div className="relative h-full">
				<div className="flex h-full gap-4 overflow-x-auto pb-2">
					{STATES.map((col) => {
						const cards = issues.filter((i) => i.state === col.key);
						const isCollapsed = collapsed.has(col.key);

						if (isCollapsed) {
							return (
								<div
									key={col.key}
									data-testid={`column-${col.key}`}
									data-collapsed="true"
									className="flex w-10 shrink-0 flex-col items-center gap-2 pt-2"
								>
									<span className={cn("size-2 rounded-full", col.dot)} />
									<span
										data-testid={`count-${col.key}`}
										className="text-xs text-muted-foreground"
									>
										{cards.length}
									</span>
									<button
										type="button"
										aria-label={`Expand ${col.label}`}
										data-testid={`expand-${col.key}`}
										onClick={() => toggleCollapse(col.key)}
										className="flex size-6 items-center justify-center rounded text-sm hover:bg-muted"
										title={`Expand ${col.label}`}
									>
										+
									</button>
								</div>
							);
						}

						return (
							<div
								key={col.key}
								data-testid={`column-${col.key}`}
								className="flex w-72 shrink-0 flex-col"
							>
								<div className="mb-2 flex items-center gap-2 px-1">
									<span className={cn("size-2 rounded-full", col.dot)} />
									<span className="text-sm font-semibold">{col.label}</span>
									<span className="text-xs text-muted-foreground">
										{cards.length}
									</span>
									<button
										type="button"
										aria-label={`Minimize ${col.label}`}
										data-testid={`minimize-${col.key}`}
										onClick={() => toggleCollapse(col.key)}
										className="ml-auto flex size-5 items-center justify-center rounded text-sm hover:bg-muted"
										title={`Minimize ${col.label}`}
									>
										−
									</button>
								</div>
								<div className="flex flex-1 flex-col gap-2 rounded-lg bg-muted/40 p-2">
									{cards.map((issue) => (
										<IssueCard
											key={issue.id}
											issue={issue}
											onClick={() => setSelected(issue.id)}
										/>
									))}
									{!cards.length && (
										<p className="px-2 py-4 text-center text-xs text-muted-foreground">
											empty
										</p>
									)}
								</div>
							</div>
						);
					})}
				</div>

				<IssueFlyout issueId={selected} onClose={closeFlyout} />
			</div>
		</DndContext>
	);
}
