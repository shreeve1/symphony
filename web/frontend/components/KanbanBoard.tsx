"use client";

import { useCallback, useState } from "react";
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
	const closeFlyout = useCallback(() => {
		setSelected(null);
		// Clear the ?issue= query param when closing via deep-link.
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
