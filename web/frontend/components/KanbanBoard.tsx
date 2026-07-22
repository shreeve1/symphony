"use client";

import { useCallback, useEffect, useState } from "react";
import {
	DndContext,
	DragOverlay,
	PointerSensor,
	useDraggable,
	useDroppable,
	useSensor,
	useSensors,
	type DragEndEvent,
	type DragStartEvent,
} from "@dnd-kit/core";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { patchIssue, type Issue } from "@/lib/api";
import { STATES, type StateKey } from "@/lib/issues";
import { isActiveRunState } from "@/lib/polling";
import { cn } from "@/lib/utils";
import { IssueCard } from "@/components/IssueCard";
import { IssueFlyout } from "@/components/IssueFlyout";

// IssueCard wrapped in a draggable. A small activation distance keeps taps
// working as clicks (open the flyout); only a real drag starts a move.
function DraggableCard({
	issue,
	onClick,
	waitingOn,
	lockConflicts,
}: {
	issue: Issue;
	onClick: () => void;
	waitingOn: number[];
	lockConflicts: string[];
}) {
	const { setNodeRef, listeners, attributes, isDragging } = useDraggable({
		id: issue.id,
	});
	return (
		<IssueCard
			issue={issue}
			onClick={onClick}
			dragRef={setNodeRef}
			dragListeners={listeners}
			dragAttributes={attributes}
			isDragging={isDragging}
			waitingOn={waitingOn}
			lockConflicts={lockConflicts}
		/>
	);
}

// One board column. Both the expanded panel and the collapsed rail are drop
// targets keyed by the column's state, so a drop onto either moves the card.
function Column({
	col,
	cards,
	isCollapsed,
	onToggle,
	onSelect,
	waitingOn,
	lockConflicts,
}: {
	col: (typeof STATES)[number];
	cards: Issue[];
	isCollapsed: boolean;
	onToggle: (key: string) => void;
	onSelect: (id: number) => void;
	waitingOn: (issue: Issue) => number[];
	lockConflicts: (issue: Issue) => string[];
}) {
	const { setNodeRef, isOver } = useDroppable({ id: col.key });

	if (isCollapsed) {
		return (
			<div
				ref={setNodeRef}
				data-testid={`column-${col.key}`}
				data-collapsed="true"
				className={cn(
					"flex w-10 shrink-0 flex-col items-center gap-2 rounded-lg pt-2",
					isOver && "ring-2 ring-foreground/30",
				)}
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
					onClick={() => onToggle(col.key)}
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
			ref={setNodeRef}
			data-testid={`column-${col.key}`}
			className="flex w-72 shrink-0 flex-col"
		>
			<div className="mb-2 flex items-center gap-2 px-1">
				<span className={cn("size-2 rounded-full", col.dot)} />
				<span className="text-sm font-semibold">{col.label}</span>
				<span className="text-xs text-muted-foreground">{cards.length}</span>
				<button
					type="button"
					aria-label={`Minimize ${col.label}`}
					data-testid={`minimize-${col.key}`}
					onClick={() => onToggle(col.key)}
					className="ml-auto flex size-5 items-center justify-center rounded text-sm hover:bg-muted"
					title={`Minimize ${col.label}`}
				>
					−
				</button>
			</div>
			<div
				className={cn(
					"flex flex-1 flex-col gap-2 rounded-lg bg-muted/40 p-2",
					isOver && "ring-2 ring-foreground/30",
				)}
			>
				{cards.map((issue) => (
					<DraggableCard
						key={issue.id}
						issue={issue}
						onClick={() => onSelect(issue.id)}
						waitingOn={waitingOn(issue)}
						lockConflicts={lockConflicts(issue)}
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
}

export function KanbanBoard({
	issues,
	initialIssueId,
	freshIssueId = null,
}: {
	issues: Issue[];
	initialIssueId?: number | null;
	freshIssueId?: number | null;
}) {
	const router = useRouter();
	const { binding } = useParams<{ binding: string }>();
	const queryClient = useQueryClient();
	const [selected, setSelected] = useState<number | null>(
		initialIssueId ?? null,
	);
	const [activeId, setActiveId] = useState<number | null>(null);

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

	// A drop changes state via the same PATCH the state chip uses. Optimistically
	// rewrite the board's query cache so the card lands immediately; roll back on
	// failure. The incoming issue.updated WS event upserts the same row by id, so
	// optimistic + live reconcile is idempotent (no double-move).
	const issuesKey = ["issues", binding];
	const move = useMutation({
		mutationFn: ({ id, state }: { id: number; state: StateKey }) =>
			patchIssue(id, { state }),
		onMutate: async ({ id, state }) => {
			await queryClient.cancelQueries({ queryKey: issuesKey });
			const previous = queryClient.getQueryData<Issue[]>(issuesKey);
			queryClient.setQueryData<Issue[]>(issuesKey, (old) =>
				old?.map((i) => (i.id === id ? { ...i, state } : i)),
			);
			return { previous };
		},
		onError: (_error, _vars, context) => {
			if (context?.previous) {
				queryClient.setQueryData(issuesKey, context.previous);
			}
		},
		onSettled: (_data, _error, { id }) => {
			queryClient.invalidateQueries({ queryKey: issuesKey });
			queryClient.invalidateQueries({ queryKey: ["issue", id] });
		},
	});

	const sensors = useSensors(
		useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
	);

	const onDragStart = useCallback((event: DragStartEvent) => {
		setActiveId(Number(event.active.id));
	}, []);

	const onDragEnd = useCallback(
		(event: DragEndEvent) => {
			setActiveId(null);
			const { active, over } = event;
			if (!over) return;
			const id = Number(active.id);
			const target = String(over.id) as StateKey;
			const issue = issues.find((i) => i.id === id);
			if (!issue || issue.state === target) return;
			move.mutate({ id, state: target });
		},
		[issues, move],
	);

	const issueById = new Map(issues.map((issue) => [issue.id, issue]));
	const activeLocks = new Set(
		issues
			.filter(
				(issue) =>
					issue.state === "running" || isActiveRunState(issue.latest_run_state),
			)
			.flatMap((issue) => issue.locks),
	);
	const waitingOn = (issue: Issue) =>
		issue.state === "todo"
			? issue.blocked_by.filter((id) => {
					const blocker = issueById.get(id);
					return blocker != null && !["done", "archived"].includes(blocker.state);
				})
			: [];
	const lockConflicts = (issue: Issue) =>
		issue.state === "todo"
			? issue.locks.filter((lock) => activeLocks.has(lock))
			: [];

	const activeIssue =
		activeId != null ? issues.find((i) => i.id === activeId) : null;

	return (
		<DndContext
			sensors={sensors}
			onDragStart={onDragStart}
			onDragEnd={onDragEnd}
			onDragCancel={() => setActiveId(null)}
		>
			<div className="relative h-full">
				<div className="flex h-full gap-4 overflow-x-auto pb-2">
					{STATES.map((col) => (
						<Column
							key={col.key}
							col={col}
							cards={issues.filter((i) => i.state === col.key)}
							isCollapsed={collapsed.has(col.key)}
							onToggle={toggleCollapse}
							onSelect={setSelected}
							waitingOn={waitingOn}
							lockConflicts={lockConflicts}
						/>
					))}
				</div>

				<IssueFlyout
					issueId={selected}
					onClose={closeFlyout}
					freshIssueId={freshIssueId}
				/>
			</div>

			<DragOverlay>
				{activeIssue ? (
					<IssueCard
						issue={activeIssue}
						waitingOn={waitingOn(activeIssue)}
						lockConflicts={lockConflicts(activeIssue)}
					/>
				) : null}
			</DragOverlay>
		</DndContext>
	);
}
