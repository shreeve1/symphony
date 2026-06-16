"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	fetchBindings,
	fetchIssue,
	fetchIssueRuns,
	fetchSkills,
	patchIssue,
	postAbort,
	postReply,
	postSteer,
	type IssueDetail,
	type IssuePatch,
	type Run,
} from "@/lib/api";
import { STATES } from "@/lib/issues";
import { isActiveRunState } from "@/lib/polling";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { RunDetailPanel } from "@/components/RunDetailPanel";
import { RunHistoryList } from "@/components/RunHistoryList";
import { SessionTailPanel } from "@/components/SessionTailPanel";
import { useAppendTailEvent } from "@/components/QueryProvider";

// Width persistence — the operator's chosen flyout width survives reopen and
// reload. The #012c spec's "~480px" is only the default; validated by the
// prototype, the panel is resizable from its left edge.
const WIDTH_KEY = "podium-flyout-width";
const DEFAULT_W = 480;
const MIN_W = 360;
const MAX_W = 900;

function useFlyoutWidth() {
	const [width, setWidth] = useState(DEFAULT_W);
	const [isMaximized, setIsMaximized] = useState(false);
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
	const toggleMaximized = useCallback(
		() => setIsMaximized((value) => !value),
		[],
	);
	const restoreNormalWidth = useCallback(() => setIsMaximized(false), []);

	return {
		panelWidth: isMaximized ? "100vw" : width,
		isMaximized,
		startDrag,
		toggleMaximized,
		restoreNormalWidth,
	};
}

// Optimistic PATCH (#013): the flyout cache updates immediately, rolls back on
// a 4xx, and both the detail and the board list refetch once the write settles.
interface PatchVariables {
	issue: IssueDetail;
	patch: IssuePatch;
}

function usePatchIssue() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ issue, patch }: PatchVariables) =>
			patchIssue(issue.id, patch),
		onMutate: async ({ issue, patch }) => {
			const key = ["issue", issue.id];
			await queryClient.cancelQueries({ queryKey: key });
			const previous = queryClient.getQueryData<IssueDetail>(key);
			queryClient.setQueryData<IssueDetail>(
				key,
				(old) => old && { ...old, ...patch },
			);
			return { previous };
		},
		onError: (_error, { issue }, context) => {
			if (context?.previous) {
				queryClient.setQueryData(["issue", issue.id], context.previous);
			}
		},
		onSettled: (_data, _error, { issue }) => {
			queryClient.invalidateQueries({ queryKey: ["issue", issue.id] });
			queryClient.invalidateQueries({
				queryKey: ["issues", issue.binding_name],
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

// Union of effort tokens across models; the model chip here is free-text (no
// per-model catalog lookup), so the dispatch gate is the enforcement point for
// an effort a given model doesn't support.
const EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh"] as const;
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
				{issue.binding_type === "infra" && (
					<>
						<ChipToggle
							label="approval"
							field="approval_required"
							value={issue.approval_required}
							onPatch={onPatch}
						/>
						<ChipToggle
							label="approved"
							field="approved"
							value={issue.approved}
							onPatch={onPatch}
						/>
						<ChipText
							label="scheduled"
							field="scheduled_for"
							value={issue.scheduled_for}
							onPatch={onPatch}
						/>
					</>
				)}
				<ChipText
					label="base"
					field="base_branch"
					value={issue.base_branch}
					onPatch={onPatch}
				/>
			</div>
			{issue.worktree_active &&
				issue.state !== "done" &&
				issue.worktree_path &&
				issue.worktree_branch && (
					<p
						data-testid="worktree-path"
						className="text-xs text-muted-foreground"
					>
						worktree: {issue.worktree_path} (branch: {issue.worktree_branch})
					</p>
				)}
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

// Operator reply composer: appends an attributed reply to the comment thread
// and flips the issue back to todo so the agent re-runs (server-side, atomic).
// Sits at the top of the comments tab, above the thread, so it never gets
// buried as Runs accumulate.
function ReplyComposer({ issue }: { issue: IssueDetail }) {
	const queryClient = useQueryClient();
	const [draft, setDraft] = useState("");
	const taRef = useRef<HTMLTextAreaElement>(null);

	// Auto-grow: start small (one row) and expand to fit the draft up to a cap,
	// after which it scrolls. Resync height whenever the draft changes (typing,
	// or the reset to "" after a successful send).
	useEffect(() => {
		const el = taRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${el.scrollHeight}px`;
	}, [draft]);

	const reply = useMutation({
		mutationFn: (body: string) => postReply(issue.id, body),
		onSuccess: () => {
			setDraft("");
			queryClient.invalidateQueries({ queryKey: ["issue", issue.id] });
			queryClient.invalidateQueries({
				queryKey: ["issues", issue.binding_name],
			});
		},
	});

	// Gate on run-state: a live or queued run can't honor a mid-run reply, and a
	// todo issue is already queued. isActiveRunState mirrors the board gating.
	const runningOrActive =
		issue.state === "running" || isActiveRunState(issue.latest_run_state);
	const isTodo = issue.state === "todo";
	const replyDisabled = runningOrActive || isTodo;
	const hint = runningOrActive
		? "Agent is running — reply when it parks for review."
		: "Already queued to run.";

	return (
		<div className="space-y-2" data-testid="reply-composer">
			<textarea
				ref={taRef}
				data-testid="reply-input"
				value={draft}
				rows={1}
				placeholder="Write a reply to the agent…"
				disabled={replyDisabled}
				onChange={(e) => setDraft(e.target.value)}
				className="max-h-60 w-full resize-none overflow-y-auto rounded-md border bg-transparent p-2 font-mono text-xs outline-none disabled:opacity-50"
			/>
			{replyDisabled && (
				<p
					data-testid="reply-disabled-hint"
					className="text-xs text-muted-foreground"
				>
					{hint}
				</p>
			)}
			{reply.isError && (
				<p data-testid="reply-error" className="text-xs text-red-500">
					Reply failed — the issue may have changed state. Try again.
				</p>
			)}
			<div className="flex justify-end">
				<button
					type="button"
					data-testid="reply-send"
					disabled={replyDisabled || reply.isPending || draft.trim() === ""}
					onClick={() => reply.mutate(draft)}
					className="rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted/40 disabled:opacity-50"
				>
					Send
				</button>
			</div>
		</div>
	);
}

function SteerComposer({
	issue,
	latestRun,
	bindingPiMode,
}: {
	issue: IssueDetail;
	latestRun: Run | null;
	bindingPiMode: "one-shot" | "rpc" | null;
}) {
	const queryClient = useQueryClient();
	const appendTail = useAppendTailEvent();
	const [draft, setDraft] = useState("");
	const [lastStatus, setLastStatus] = useState<string | null>(null);
	const taRef = useRef<HTMLTextAreaElement>(null);

	useEffect(() => {
		const el = taRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${el.scrollHeight}px`;
	}, [draft]);

	const latestRunAgent = latestRun?.agent?.trim().toLowerCase() ?? null;
	const liveRun =
		issue.state === "running" &&
		issue.latest_run_state === "running" &&
		issue.latest_run_id != null;
	const canSteer =
		liveRun && latestRunAgent === "pi" && bindingPiMode === "rpc";
	const disabledReason = !liveRun
		? "Live steering is available only while a pi RPC run is active."
		: latestRun == null
			? "Loading latest run details…"
			: latestRunAgent === "claude"
				? "Claude runs use park-and-reply only."
				: bindingPiMode !== "rpc"
					? "This binding is not using pi RPC live steering."
					: "Live steering is available only for pi RPC runs.";

	const appendLocalTail = (payload: Record<string, unknown>) => {
		appendTail({ issue_id: issue.id, lines: [JSON.stringify(payload)] });
	};
	const invalidateIssue = () => {
		queryClient.invalidateQueries({ queryKey: ["issue", issue.id] });
		queryClient.invalidateQueries({ queryKey: ["issues", issue.binding_name] });
	};

	const steer = useMutation({
		mutationFn: (body: string) => postSteer(issue.id, body),
		onMutate: (body) => {
			appendLocalTail({ type: "operator_steer", state: "queued", body });
			setLastStatus("Steer queued");
		},
		onSuccess: (_data, body) => {
			setDraft("");
			appendLocalTail({ type: "operator_steer", state: "delivered", body });
			setLastStatus("Steer delivered");
			invalidateIssue();
		},
		onError: (_error, body) => {
			appendLocalTail({ type: "operator_steer", state: "failed", body });
			setLastStatus("Steer failed");
		},
	});
	const abort = useMutation({
		mutationFn: () => postAbort(issue.id),
		onMutate: () => {
			appendLocalTail({ type: "operator_abort", state: "queued" });
			setLastStatus("Abort queued");
		},
		onSuccess: () => {
			appendLocalTail({ type: "operator_abort", state: "delivered" });
			setLastStatus("Abort delivered");
			invalidateIssue();
		},
		onError: () => {
			appendLocalTail({ type: "operator_abort", state: "failed" });
			setLastStatus("Abort failed");
		},
	});
	const isPending = steer.isPending || abort.isPending;

	return (
		<div
			className="space-y-2 rounded-md border p-3"
			data-testid="steer-composer"
		>
			<div className="flex items-center justify-between gap-2">
				<div>
					<p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
						Live steering
					</p>
					{!canSteer && (
						<p
							data-testid="steer-disabled-hint"
							className="text-xs text-muted-foreground"
						>
							{disabledReason}
						</p>
					)}
					{lastStatus && (
						<p
							data-testid="steer-status"
							className="text-xs text-muted-foreground"
						>
							{lastStatus}
						</p>
					)}
				</div>
				<button
					type="button"
					data-testid="steer-abort"
					disabled={!canSteer || isPending}
					onClick={() => abort.mutate()}
					className="rounded-md border border-red-300 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
				>
					Abort
				</button>
			</div>
			<textarea
				ref={taRef}
				data-testid="steer-input"
				value={draft}
				rows={1}
				placeholder="Redirect the running pi agent…"
				disabled={!canSteer || isPending}
				onChange={(e) => setDraft(e.target.value)}
				className="max-h-40 w-full resize-none overflow-y-auto rounded-md border bg-transparent p-2 font-mono text-xs outline-none disabled:opacity-50"
			/>
			{(steer.isError || abort.isError) && (
				<p data-testid="steer-error" className="text-xs text-red-500">
					Steer request failed — the run may have finished or changed agent.
				</p>
			)}
			<div className="flex justify-end">
				<button
					type="button"
					data-testid="steer-send"
					disabled={!canSteer || isPending || draft.trim() === ""}
					onClick={() => steer.mutate(draft)}
					className="rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted/40 disabled:opacity-50"
				>
					Send steer
				</button>
			</div>
		</div>
	);
}

// Comments are stored as one chronological markdown blob (oldest first); each
// entry is an appended block headed `### Operator Reply (…)` or `### Symphony AI
// Summary`. Render the blob straight through so the headings act as the natural
// separators, and auto-scroll to the newest entry when the flyout opens. Keeps
// the `view-comments_md` testid as the container so existing coverage (text
// presence) still holds.
function CommentsThread({
	issueId,
	source,
}: {
	issueId: number;
	source: string;
}) {
	const scrollRef = useRef<HTMLDivElement>(null);
	// Land on the newest comment when the flyout opens. Keyed on issueId (not
	// source) so a background poll never yanks the operator down mid-read.
	useEffect(() => {
		const el = scrollRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [issueId]);
	const hasComments = source.trim().length > 0;
	return (
		<div
			ref={scrollRef}
			data-testid="view-comments_md"
			className="max-h-[60vh] overflow-y-auto"
		>
			{hasComments ? (
				<div className="rounded-md border p-2">
					<Markdown source={source} />
				</div>
			) : (
				<p className="rounded-md border p-2 text-xs text-muted-foreground">
					No comments yet.
				</p>
			)}
		</div>
	);
}

const TABS = ["comments", "session"] as const;
type Tab = (typeof TABS)[number];

export function IssueFlyout({
	issueId,
	onClose,
}: {
	issueId: number | null;
	onClose: () => void;
}) {
	const {
		panelWidth,
		isMaximized,
		startDrag,
		toggleMaximized,
		restoreNormalWidth,
	} = useFlyoutWidth();
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
	const patch = usePatchIssue();
	const onPatch: OnPatch = (issuePatch) => {
		if (detail.data) patch.mutate({ issue: detail.data, patch: issuePatch });
	};
	// Skill catalog feeds the preferred_skill picker; free text would 422
	// against the FK and silently roll back.
	const skills = useQuery({ queryKey: ["skills"], queryFn: fetchSkills });
	const bindings = useQuery({ queryKey: ["bindings"], queryFn: fetchBindings });
	const skillNames = (skills.data ?? []).map((s) => s.name);
	const showEmptySkillHint = skills.isSuccess && skillNames.length === 0;

	// Reset nested flyout state each time a different issue opens.
	useEffect(() => {
		setTab("comments");
		setSelectedRunId(null);
		restoreNormalWidth();
	}, [issueId, restoreNormalWidth]);

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
	const latestRun =
		issue && runs.data
			? (runs.data.find((run) => run.id === issue.latest_run_id) ?? null)
			: null;
	const bindingPiMode =
		issue && bindings.data
			? (bindings.data.find((binding) => binding.name === issue.binding_name)
					?.pi_mode ?? null)
			: null;

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
				style={{ width: panelWidth }}
				className="fixed inset-y-0 right-0 z-50 flex overflow-hidden border-l bg-background shadow-xl outline-none"
			>
				{/* Resize handle — drag the left edge. Lives on the non-scrolling
            wrapper so it stays put while the body scrolls. */}
				{!isMaximized && (
					<div
						onPointerDown={startDrag}
						className="group absolute inset-y-0 left-0 z-10 w-1.5 cursor-ew-resize"
						role="separator"
						aria-orientation="vertical"
					>
						<div className="h-full w-px bg-border transition-colors group-hover:w-0.5 group-hover:bg-foreground/40" />
					</div>
				)}

				<div className="flex-1 overflow-y-auto">
					{detail.isError ? (
						<p className="p-6 text-sm text-red-500">
							Failed to load this issue.
						</p>
					) : !issue ? (
						<p className="p-6 text-sm text-muted-foreground">Loading…</p>
					) : (
						<div className="space-y-4 p-6">
							<div className="flex items-start justify-between gap-3">
								<h2
									id="flyout-title"
									className="text-lg font-semibold leading-tight"
									data-testid="flyout-title"
								>
									{issue.title}
								</h2>
								<div className="flex shrink-0 gap-2">
									<button
										type="button"
										data-testid="toggle-flyout-maximize"
										aria-pressed={isMaximized}
										onClick={toggleMaximized}
										className="rounded-md border px-3 py-1.5 text-sm"
									>
										{isMaximized ? "Restore" : "Maximize"}
									</button>
									<button
										type="button"
										data-testid="close-issue-flyout"
										onClick={onClose}
										className="rounded-md border px-3 py-1.5 text-sm"
									>
										Close
									</button>
								</div>
							</div>

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
									{tab === "comments" ? (
										// Reply composer on top so it never gets buried as Runs
										// accumulate; thread below renders oldest-first,
										// scrolled to the newest entry on open.
										<div className="space-y-3">
											<ReplyComposer issue={issue} />
											<CommentsThread
												issueId={issue.id}
												source={issue.comments_md}
											/>
										</div>
									) : (
										<div className="space-y-3">
											<SteerComposer
												issue={issue}
												latestRun={latestRun}
												bindingPiMode={bindingPiMode}
											/>
											<SessionTailPanel issueId={issue.id} />
										</div>
									)}
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
