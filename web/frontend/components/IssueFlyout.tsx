"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	fetchIssue,
	fetchIssueRuns,
	fetchSkills,
	patchIssue,
	type IssueDetail,
	type IssuePatch,
} from "@/lib/api";
import { STATES } from "@/lib/issues";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { RunDetailPanel } from "@/components/RunDetailPanel";
import { RunHistoryList } from "@/components/RunHistoryList";

// Width persistence — the operator's chosen flyout width survives reopen and
// reload. The #012c spec's "~480px" is only the default; validated by the
// prototype, the panel is resizable from its left edge.
const WIDTH_KEY = "podium-flyout-width";
const DEFAULT_W = 480;
const MIN_W = 360;
const MAX_W = 900;

function useFlyoutWidth() {
	const [width, setWidth] = useState(DEFAULT_W);
	// Tracks the teardown for an in-flight drag so a mid-drag unmount can't leak
	// window listeners (or fire onUp on an unmounted component).
	const cleanupRef = useRef<(() => void) | null>(null);

	useEffect(() => {
		const saved = Number(window.localStorage.getItem(WIDTH_KEY));
		if (saved >= MIN_W && saved <= MAX_W) setWidth(saved);
	}, []);

	useEffect(() => () => cleanupRef.current?.(), []);

	const startDrag = useCallback((e: React.PointerEvent) => {
		e.preventDefault();
		const clamp = (x: number) =>
			Math.min(MAX_W, Math.max(MIN_W, window.innerWidth - x));
		const onMove = (ev: PointerEvent) => setWidth(clamp(ev.clientX));
		const teardown = () => {
			window.removeEventListener("pointermove", onMove);
			window.removeEventListener("pointerup", onUp);
			document.body.style.userSelect = "";
			cleanupRef.current = null;
		};
		const onUp = (ev: PointerEvent) => {
			window.localStorage.setItem(
				WIDTH_KEY,
				String(Math.round(clamp(ev.clientX))),
			);
			teardown();
		};
		cleanupRef.current = teardown;
		document.body.style.userSelect = "none";
		window.addEventListener("pointermove", onMove);
		window.addEventListener("pointerup", onUp);
	}, []);

	return { width, startDrag };
}

// Optimistic PATCH (#013): the flyout cache updates immediately, rolls back on
// a 4xx, and both the detail and the board list refetch once the write settles.
function usePatchIssue(issue: IssueDetail | undefined) {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (patch: IssuePatch) => patchIssue(issue!.id, patch),
		onMutate: async (patch) => {
			const key = ["issue", issue!.id];
			await queryClient.cancelQueries({ queryKey: key });
			const previous = queryClient.getQueryData<IssueDetail>(key);
			queryClient.setQueryData<IssueDetail>(
				key,
				(old) => old && { ...old, ...patch },
			);
			return { previous };
		},
		onError: (_error, _patch, context) => {
			if (context?.previous) {
				queryClient.setQueryData(["issue", issue!.id], context.previous);
			}
		},
		onSettled: () => {
			queryClient.invalidateQueries({ queryKey: ["issue", issue!.id] });
			queryClient.invalidateQueries({
				queryKey: ["issues", issue!.binding_name],
			});
		},
	});
}

// Local draft that resyncs when the server value changes (refetch, rollback,
// switching issues) but never clobbers in-progress typing while it is stable.
function useDraft(value: string) {
	const [draft, setDraft] = useState(value);
	const synced = useRef(value);
	useEffect(() => {
		if (value !== synced.current) {
			synced.current = value;
			setDraft(value);
		}
	}, [value]);
	return [draft, setDraft] as const;
}

type OnPatch = (patch: IssuePatch) => void;

function ChipShell({
	label,
	children,
}: {
	label: string;
	children: React.ReactNode;
}) {
	return (
		<span className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-1 text-xs">
			<span className="text-muted-foreground">{label}</span>
			{children}
		</span>
	);
}

function ChipSelect({
	label,
	field,
	value,
	options,
	allowEmpty = false,
	onPatch,
}: {
	label: string;
	field: keyof IssuePatch;
	value: string | null;
	options: readonly string[];
	allowEmpty?: boolean;
	onPatch: OnPatch;
}) {
	return (
		<ChipShell label={label}>
			<select
				data-testid={`edit-${field}`}
				value={value ?? ""}
				onChange={(e) =>
					onPatch({ [field]: e.target.value === "" ? null : e.target.value })
				}
				className="cursor-pointer bg-transparent font-medium outline-none"
			>
				{allowEmpty && <option value="">—</option>}
				{/* Keep the current value selectable even when it's missing from
            options (e.g. skill catalog still loading, or a stale name). */}
				{value != null && !options.includes(value) && (
					<option value={value}>{value}</option>
				)}
				{options.map((option) => (
					<option key={option} value={option}>
						{option}
					</option>
				))}
			</select>
		</ChipShell>
	);
}

function ChipText({
	label,
	field,
	value,
	onPatch,
}: {
	label: string;
	field: keyof IssuePatch;
	value: string | null;
	onPatch: OnPatch;
}) {
	const [draft, setDraft] = useDraft(value ?? "");
	const commit = () => {
		const next = draft.trim() === "" ? null : draft.trim();
		if (next !== (value ?? null)) onPatch({ [field]: next });
	};
	return (
		<ChipShell label={label}>
			<input
				data-testid={`edit-${field}`}
				value={draft}
				placeholder="—"
				size={Math.max(4, draft.length)}
				onChange={(e) => setDraft(e.target.value)}
				onBlur={commit}
				onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
				className="bg-transparent font-medium outline-none"
			/>
		</ChipShell>
	);
}

function ChipToggle({
	label,
	field,
	value,
	onPatch,
}: {
	label: string;
	field: keyof IssuePatch;
	value: boolean;
	onPatch: OnPatch;
}) {
	return (
		<ChipShell label={label}>
			<button
				type="button"
				data-testid={`edit-${field}`}
				aria-pressed={value}
				onClick={() => onPatch({ [field]: !value })}
				className="font-medium"
			>
				{value ? "active" : "off"}
			</button>
		</ChipShell>
	);
}

const EFFORTS = ["minimal", "low", "medium", "high"] as const;
const STATE_KEYS = STATES.map((s) => s.key);

function MetadataChips({
	issue,
	skillNames,
	showEmptySkillHint,
	onPatch,
}: {
	issue: IssueDetail;
	skillNames: readonly string[];
	showEmptySkillHint: boolean;
	onPatch: OnPatch;
}) {
	return (
		<div className="space-y-1.5">
			<div className="flex flex-wrap gap-1.5" data-testid="metadata-chips">
				<ChipSelect
					label="state"
					field="state"
					value={issue.state}
					options={STATE_KEYS}
					onPatch={onPatch}
				/>
				<ChipSelect
					label="skill"
					field="preferred_skill"
					value={issue.preferred_skill}
					options={skillNames}
					allowEmpty
					onPatch={onPatch}
				/>
				<ChipText
					label="agent"
					field="preferred_agent"
					value={issue.preferred_agent}
					onPatch={onPatch}
				/>
				<ChipText
					label="model"
					field="preferred_model"
					value={issue.preferred_model}
					onPatch={onPatch}
				/>
				<ChipSelect
					label="effort"
					field="reasoning_effort"
					value={issue.reasoning_effort}
					options={EFFORTS}
					onPatch={onPatch}
				/>
				<ChipToggle
					label="worktree"
					field="worktree_active"
					value={issue.worktree_active}
					onPatch={onPatch}
				/>
				<ChipText
					label="base"
					field="base_branch"
					value={issue.base_branch}
					onPatch={onPatch}
				/>
			</div>
			{showEmptySkillHint && (
				<p
					data-testid="skill-catalog-empty"
					className="text-xs text-muted-foreground"
				>
					Run `podium skills refresh` to populate.
				</p>
			)}
		</div>
	);
}

// Markdown blob editor: plain textarea committing on blur, with a side-by-side
// preview pane on toggle (no live render, per the #013 spec).
function MarkdownEditor({
	value,
	field,
	onPatch,
}: {
	value: string;
	field: "comments_md" | "context_md";
	onPatch: OnPatch;
}) {
	const [draft, setDraft] = useDraft(value);
	const [preview, setPreview] = useState(false);
	const commit = () => {
		if (draft !== value) onPatch({ [field]: draft });
	};
	return (
		<div className="space-y-2">
			<div className="flex justify-end">
				<button
					type="button"
					data-testid={`preview-${field}`}
					aria-pressed={preview}
					onClick={() => setPreview((p) => !p)}
					className="rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
				>
					Preview
				</button>
			</div>
			<div className="flex gap-3">
				<textarea
					data-testid={`edit-${field}`}
					value={draft}
					rows={10}
					onChange={(e) => setDraft(e.target.value)}
					onBlur={commit}
					className="min-h-40 flex-1 rounded-md border bg-transparent p-2 font-mono text-xs outline-none"
				/>
				{preview && (
					<div
						data-testid={`preview-pane-${field}`}
						className="min-h-40 flex-1 overflow-y-auto rounded-md border p-2"
					>
						<Markdown source={draft} />
					</div>
				)}
			</div>
		</div>
	);
}

const TABS = ["comments", "context"] as const;
type Tab = (typeof TABS)[number];

export function IssueFlyout({
	issueId,
	onClose,
}: {
	issueId: number | null;
	onClose: () => void;
}) {
	const { width, startDrag } = useFlyoutWidth();
	const [tab, setTab] = useState<Tab>("comments");
	const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
	const panelRef = useRef<HTMLElement | null>(null);

	const detail = useQuery({
		queryKey: ["issue", issueId],
		queryFn: () => fetchIssue(issueId as number),
		enabled: issueId != null,
	});
	const runs = useQuery({
		queryKey: ["runs", issueId],
		queryFn: () => fetchIssueRuns(issueId as number),
		enabled: issueId != null,
	});
	const patch = usePatchIssue(detail.data);
	const onPatch: OnPatch = patch.mutate;
	// Skill catalog feeds the preferred_skill picker; free text would 422
	// against the FK and silently roll back.
	const skills = useQuery({ queryKey: ["skills"], queryFn: fetchSkills });
	const skillNames = (skills.data ?? []).map((s) => s.name);
	const showEmptySkillHint = skills.isSuccess && skillNames.length === 0;

	// Reset nested flyout state each time a different issue opens.
	useEffect(() => {
		setTab("comments");
		setSelectedRunId(null);
	}, [issueId]);

	// Escape closes (click-outside is handled by the backdrop).
	useEffect(() => {
		if (issueId == null) return;
		const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [issueId, onClose]);

	// Focus management: move focus into the panel on open, restore it on close.
	useEffect(() => {
		if (issueId == null) return;
		const previouslyFocused = document.activeElement as HTMLElement | null;
		panelRef.current?.focus();
		return () => previouslyFocused?.focus?.();
	}, [issueId]);

	if (issueId == null) return null;

	const issue = detail.data;

	return (
		<>
			<div
				data-testid="flyout-backdrop"
				className="fixed inset-0 z-40 bg-black/20"
				onClick={onClose}
			/>
			<aside
				ref={panelRef}
				data-testid="issue-flyout"
				role="dialog"
				aria-modal="true"
				aria-labelledby="flyout-title"
				tabIndex={-1}
				style={{ width }}
				className="fixed inset-y-0 right-0 z-50 flex overflow-hidden border-l bg-background shadow-xl outline-none"
			>
				{/* Resize handle — drag the left edge. Lives on the non-scrolling
            wrapper so it stays put while the body scrolls. */}
				<div
					onPointerDown={startDrag}
					className="group absolute inset-y-0 left-0 z-10 w-1.5 cursor-ew-resize"
					role="separator"
					aria-orientation="vertical"
				>
					<div className="h-full w-px bg-border transition-colors group-hover:w-0.5 group-hover:bg-foreground/40" />
				</div>

				<div className="flex-1 overflow-y-auto">
					{detail.isError ? (
						<p className="p-6 text-sm text-red-500">
							Failed to load this issue.
						</p>
					) : !issue ? (
						<p className="p-6 text-sm text-muted-foreground">Loading…</p>
					) : (
						<div className="space-y-4 p-6">
							<h2
								id="flyout-title"
								className="text-lg font-semibold leading-tight"
								data-testid="flyout-title"
							>
								{issue.title}
							</h2>

							{issue.description && (
								<div className="text-muted-foreground">
									<Markdown source={issue.description} />
								</div>
							)}

							<MetadataChips
								issue={issue}
								skillNames={skillNames}
								showEmptySkillHint={showEmptySkillHint}
								onPatch={onPatch}
							/>

							<div>
								<div
									className="flex gap-1 border-b"
									role="tablist"
									aria-label="Issue detail"
								>
									{TABS.map((t) => (
										<button
											key={t}
											type="button"
											id={`tab-${t}`}
											role="tab"
											aria-selected={tab === t}
											aria-controls="issue-tabpanel"
											data-testid={`tab-${t}`}
											onClick={() => setTab(t)}
											className={cn(
												"border-b-2 px-3 py-1.5 text-sm capitalize",
												tab === t
													? "border-foreground font-medium"
													: "border-transparent text-muted-foreground hover:text-foreground",
											)}
										>
											{t}
										</button>
									))}
								</div>
								<div
									id="issue-tabpanel"
									role="tabpanel"
									aria-labelledby={`tab-${tab}`}
									className="pt-3"
									data-testid={`tabpanel-${tab}`}
								>
									{/* key resets the draft when switching tabs or issues, so an
                      uncommitted comments draft can't bleed into context. */}
									<MarkdownEditor
										key={`${issue.id}-${tab}`}
										field={tab === "comments" ? "comments_md" : "context_md"}
										value={
											tab === "comments" ? issue.comments_md : issue.context_md
										}
										onPatch={onPatch}
									/>
								</div>
							</div>

							<div>
								<h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
									Run history
								</h3>
								{runs.isError ? (
									<p className="text-xs text-red-500">Failed to load runs.</p>
								) : (
									<RunHistoryList
										runs={runs.data ?? []}
										onSelectRun={setSelectedRunId}
									/>
								)}
							</div>
						</div>
					)}
				</div>
				{selectedRunId != null && (
					<RunDetailPanel
						runId={selectedRunId}
						onClose={() => setSelectedRunId(null)}
					/>
				)}
			</aside>
		</>
	);
}
