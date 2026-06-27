"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	fetchBindings,
	fetchIssue,
	fetchIssueOptions,
	fetchIssueRuns,
	fetchSkills,
	patchIssue,
	postAbort,
	postComment,
	postReply,
	postSteer,
	scheduleIssue,
	unscheduleIssue,
	type IssueDetail,
	type IssuePatch,
	type ModelOption,
	type Run,
} from "@/lib/api";
import { STATES } from "@/lib/issues";
import {
	isActiveRunState,
	issueDetailRefetchIntervalMs,
	runListRefetchIntervalMs,
} from "@/lib/polling";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { RunDetailPanel } from "@/components/RunDetailPanel";
import {
	DEFAULT_SCHEDULE_REASON,
	latestScheduleNotBefore,
} from "@/components/ScheduleControl";
import { RunHistoryList } from "@/components/RunHistoryList";
import { SessionTailPanel } from "@/components/SessionTailPanel";
import { useAppendTailEvent } from "@/components/QueryProvider";

// Width persistence — the operator's chosen flyout width survives reopen and
// reload. The #012c spec's "~480px" is only the default; validated by the
// prototype, the panel is resizable from its left edge.
const WIDTH_KEY = "podium-flyout-width";
const MAXIMIZED_KEY = "podium-flyout-maximized";
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
		try {
			const saved = Number(window.localStorage.getItem(WIDTH_KEY));
			if (saved >= MIN_W && saved <= MAX_W) setWidth(saved);
			setIsMaximized(window.localStorage.getItem(MAXIMIZED_KEY) === "true");
		} catch {
			// Storage unavailable — keep defaults.
		}
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
	const toggleMaximized = useCallback(() => {
		setIsMaximized((value) => {
			const next = !value;
			try {
				window.localStorage.setItem(MAXIMIZED_KEY, String(next));
			} catch {
				// Storage unavailable — in-memory state still works for this session.
			}
			return next;
		});
	}, []);

	return {
		panelWidth: isMaximized ? "100vw" : width,
		isMaximized,
		startDrag,
		toggleMaximized,
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

type ComboOption = { value: string; label?: string };

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
	options: readonly string[] | readonly ComboOption[];
	allowEmpty?: boolean;
	onPatch: OnPatch;
}) {
	const entries: ComboOption[] =
		typeof options[0] === "string"
			? (options as readonly string[]).map((o) => ({ value: o }))
			: [...(options as readonly ComboOption[])];
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
				{value != null && !entries.some((o) => o.value === value) && (
					<option value={value}>{value}</option>
				)}
				{entries.map((option) => (
					<option key={option.value} value={option.value}>
						{option.label ?? option.value}
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

type ScheduleMode = "none" | "next_window";

interface StagedDispatchControls {
	scheduleMode: ScheduleMode | null;
	approval_required: boolean | null;
	approved: boolean | null;
}

const EMPTY_STAGED_DISPATCH: StagedDispatchControls = {
	scheduleMode: null,
	approval_required: null,
	approved: null,
};

function scheduleModeFor(issue: IssueDetail): ScheduleMode {
	return issue.scheduled_for ? "next_window" : "none";
}

// modelOptionValue returns the value to store in preferred_model for a
// catalog entry, disambiguating with provider when the same model id appears
// under more than one agent (e.g. claude-opus-4-8 for both pi/cliproxy and
// claude native). Matches the logic in NewIssueModal.modelValue.
function modelOptionValue(option: ModelOption, models: readonly ModelOption[]) {
	const duplicateId = models.some(
		(other) => other !== option && other.id === option.id,
	);
	return duplicateId && option.provider
		? `${option.provider}/${option.id}`
		: option.id;
}

function modelOptionsForAgent(
	models: readonly ModelOption[],
	agent: string | null,
): ComboOption[] {
	return models
		.filter((m) => !agent || m.agent === agent)
		.map((m) => {
			const value = modelOptionValue(m, models);
			return {
				value,
				label: m.label ? `${m.label} (${value})` : value,
			};
		});
}

function hasStagedDispatch(staged: StagedDispatchControls): boolean {
	return (
		staged.scheduleMode != null ||
		staged.approval_required != null ||
		staged.approved != null
	);
}

// Schedule is a dispatch-affecting control. The flyout stages it locally and
// applies it from the Send button, so changing Yes/No cannot move the card yet.
function ScheduleChip({
	issue,
	value,
	onChange,
	disabled,
	staged,
}: {
	issue: IssueDetail;
	value: ScheduleMode;
	onChange: (mode: ScheduleMode) => void;
	disabled: boolean;
	staged: boolean;
}) {
	const currentNotBefore = issue.scheduled_for
		? (latestScheduleNotBefore(issue.comments_md) ?? issue.scheduled_for)
		: null;
	return (
		<span data-testid="issue-schedule">
			<ChipShell label="schedule">
				<select
					data-testid="issue-schedule-mode"
					value={value}
					disabled={disabled}
					title={
						staged
							? "Pending until Send"
							: currentNotBefore
								? `Scheduled for ${currentNotBefore}`
								: undefined
					}
					onChange={(e) => onChange(e.target.value as ScheduleMode)}
					className="cursor-pointer bg-transparent font-medium outline-none disabled:opacity-50"
				>
					<option value="none">No</option>
					<option value="next_window">Yes</option>
				</select>
				{staged && <span className="font-medium text-amber-600">pending</span>}
			</ChipShell>
		</span>
	);
}

// Union of effort tokens across models; the model chip here is free-text (no
// per-model catalog lookup), so the dispatch gate is the enforcement point for
// an effort a given model doesn't support.
const EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh"] as const;
const STATE_KEYS = STATES.map((s) => s.key);

function GateHints({ issue }: { issue: IssueDetail }) {
	if (issue.state !== "todo") return null;
	// Some write endpoints (reply/comment/steer/abort/schedule/dismiss) and their
	// websocket payloads may not run _decorate_issue_gates, so these fields can be
	// absent on a freshly-mutated row. Default to [] so a re-render never throws.
	const waitingOn = issue.unsatisfied_blocked_by ?? [];
	const lockConflicts = issue.lock_conflicts ?? [];
	return (
		<div className="flex flex-wrap gap-1.5">
			{waitingOn.length > 0 && (
				<span
					data-testid="waiting-chip"
					className="rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800"
				>
					Waiting on {waitingOn.map((id) => `#${id}`).join(", ")}
				</span>
			)}
			{lockConflicts.length > 0 && (
				<span
					data-testid="lock-chip"
					className="rounded-md bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700"
				>
					Locked: {lockConflicts.join(", ")}
				</span>
			)}
		</div>
	);
}

function MetadataChips({
	issue,
	skillNames,
	modelOptions,
	showEmptySkillHint,
	onPatch,
	staged,
	approvalEnabled,
	onStageApprovalRequired,
	onStageApproved,
	onStageSchedule,
	stagedPending,
}: {
	issue: IssueDetail;
	skillNames: readonly string[];
	modelOptions: readonly ComboOption[];
	showEmptySkillHint: boolean;
	onPatch: OnPatch;
	staged: StagedDispatchControls;
	approvalEnabled: boolean;
	onStageApprovalRequired: (value: boolean) => void;
	onStageApproved: (value: boolean) => void;
	onStageSchedule: (mode: ScheduleMode) => void;
	stagedPending: boolean;
}) {
	const scheduleMode = staged.scheduleMode ?? scheduleModeFor(issue);
	const scheduleStaged = staged.scheduleMode != null;
	const approvalRequired = staged.approval_required ?? issue.approval_required;
	const approvalRequiredStaged = staged.approval_required != null;
	const approved = staged.approved ?? issue.approved;
	const approvedStaged = staged.approved != null;
	return (
		<div className="space-y-1.5">
			<GateHints issue={issue} />
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
				<ChipSelect
					label="model"
					field="preferred_model"
					value={issue.preferred_model}
					options={modelOptions}
					allowEmpty
					onPatch={onPatch}
				/>
				<ChipSelect
					label="effort"
					field="reasoning_effort"
					value={issue.reasoning_effort}
					options={EFFORTS}
					onPatch={onPatch}
				/>
				{issue.binding_type === "infra" && (
					<>
						{approvalEnabled && (
							<>
								<ChipToggle
									label={approvalRequiredStaged ? "approval*" : "approval"}
									field="approval_required"
									value={approvalRequired}
									onPatch={() => onStageApprovalRequired(!approvalRequired)}
								/>
								<ChipToggle
									label={approvedStaged ? "approved*" : "approved"}
									field="approved"
									value={approved}
									onPatch={() => onStageApproved(!approved)}
								/>
							</>
						)}
						<ScheduleChip
							issue={issue}
							value={scheduleMode}
							onChange={onStageSchedule}
							disabled={stagedPending}
							staged={scheduleStaged}
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
function ReplyComposer({
	issue,
	staged,
	onClearStaged,
	onSent,
}: {
	issue: IssueDetail;
	staged: StagedDispatchControls;
	onClearStaged: () => void;
	onSent: () => void;
}) {
	const queryClient = useQueryClient();
	const [draft, setDraft] = useState("");
	const taRef = useRef<HTMLTextAreaElement>(null);
	const hasStaged = hasStagedDispatch(staged);

	// Auto-grow: start small (one row) and expand to fit the draft up to a cap,
	// after which it scrolls. Resync height whenever the draft changes (typing,
	// or the reset to "" after a successful send).
	useEffect(() => {
		const el = taRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${el.scrollHeight}px`;
	}, [draft]);

	// Gate on run-state: a live or queued run can't honor a mid-run reply, and a
	// todo issue is already queued. isActiveRunState mirrors the board gating.
	const runningOrActive =
		issue.state === "running" || isActiveRunState(issue.latest_run_state);
	const isTodo = issue.state === "todo";
	// A scheduled issue sits in todo until its maintenance window. /reply would
	// re-dispatch it early (and 409 on todo), so post an append-only comment
	// instead — the operator can annotate the held issue without disturbing it.
	const commentMode =
		(isTodo && issue.scheduled_for != null && !runningOrActive) ||
		staged.scheduleMode != null;
	const replyDisabled =
		runningOrActive || (isTodo && !commentMode && !hasStaged);
	const hint = runningOrActive
		? "Agent is running — reply when it parks for review."
		: hasStaged
			? "Press Send to apply the staged controls."
			: "Already queued to run.";

	const reply = useMutation({
		mutationFn: async (body: string) => {
			let result: IssueDetail | null = null;
			const approvalPatch: IssuePatch = {};
			if (staged.approval_required != null) {
				approvalPatch.approval_required = staged.approval_required;
			}
			if (staged.approved != null) approvalPatch.approved = staged.approved;
			if (Object.keys(approvalPatch).length > 0) {
				result = await patchIssue(issue.id, approvalPatch);
			}

			const text = body.trim();
			if (staged.scheduleMode != null) {
				if (text) result = await postComment(issue.id, body);
				result =
					staged.scheduleMode === "next_window"
						? await scheduleIssue(issue.id, {
								not_before: "next_window",
								reason: DEFAULT_SCHEDULE_REASON,
							})
						: await unscheduleIssue(issue.id);
				return result;
			}

			if (!text) return result ?? issue;
			return commentMode
				? postComment(issue.id, body)
				: postReply(issue.id, body);
		},
		onSuccess: () => {
			setDraft("");
			onClearStaged();
			queryClient.invalidateQueries({ queryKey: ["issue", issue.id] });
			queryClient.invalidateQueries({
				queryKey: ["issues", issue.binding_name],
			});
			onSent();
		},
	});

	return (
		<div className="space-y-2" data-testid="reply-composer">
			<textarea
				ref={taRef}
				data-testid="reply-input"
				value={draft}
				rows={1}
				placeholder={
					hasStaged
						? "Comment, then Send to apply staged controls…"
						: commentMode
							? "Add a comment (held until window — won't re-run the agent)…"
							: "Write a reply to the agent…"
				}
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
					disabled={
						replyDisabled ||
						reply.isPending ||
						(!hasStaged && draft.trim() === "")
					}
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
	bindingClaudePersist,
}: {
	issue: IssueDetail;
	latestRun: Run | null;
	bindingPiMode: "one-shot" | "rpc" | null;
	bindingClaudePersist: boolean | null;
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
	const isClaudeRun = liveRun && latestRunAgent === "claude";
	const canSteer =
		liveRun &&
		((latestRunAgent === "pi" && bindingPiMode === "rpc") ||
			(latestRunAgent === "claude" && bindingClaudePersist === true));
	const disabledReason = !liveRun
		? "Live steering is available only while a pi RPC run is active."
		: latestRun == null
			? "Loading latest run details…"
			: latestRunAgent === "claude"
				? "Claude live steering requires claude_persist; otherwise use park-and-reply."
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
					{isClaudeRun && (
						<p
							data-testid="steer-agent-copy"
							className="text-xs text-muted-foreground"
						>
							Steer is queued; Claude picks it up at its next turn. Abort:
							interrupt the current turn now (Esc).
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
				placeholder={
					isClaudeRun
						? "Queue guidance for Claude’s next turn…"
						: "Redirect the running pi agent…"
				}
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
// entry is an appended block headed by a known marker. The blob is rendered
// straight through (no sub-heading split) so a multi-heading summary is never
// shredded. Keeps the `view-comments_md` testid as the container so existing
// coverage (text presence) still holds.
//
// Both agent run summaries and operator replies stack up one-per-run/reply, so
// we collapse them to only the most recent entry of each kind — older ones
// stay in Run history. Patrol entries (`### Patrol`) and any non-agent text
// are always shown.
const AGENT_SUMMARY_MARKERS = [
	"**Symphony completed:**",
	"**Symphony question:**",
	"### Symphony AI Summary",
] as const;

const OPERATOR_MARKERS = [
	"### Operator Reply (",
	"### Operator Steer (",
	"### Operator Abort (",
] as const;

// Split only at known entry headers, never at arbitrary sub-headings, so a
// summary containing `### …` sections is not broken into pieces.
const ENTRY_BOUNDARY =
	/\n+(?=### Operator Reply \(|### Operator Steer \(|### Operator Abort \(|### Patrol \(|### Symphony AI Summary|\*\*Symphony completed:\*\*|\*\*Symphony question:\*\*)/;

function isAgentSummary(entry: string): boolean {
	return AGENT_SUMMARY_MARKERS.some((marker) => entry.startsWith(marker));
}

function isOperatorEntry(entry: string): boolean {
	return OPERATOR_MARKERS.some((marker) => entry.startsWith(marker));
}

function collapseCompletions(source: string): {
	text: string;
	hiddenAgentCount: number;
	hiddenOperatorCount: number;
} {
	const entries = source.split(ENTRY_BOUNDARY);
	let lastAgentIndex = -1;
	let lastOperatorIndex = -1;
	entries.forEach((entry, index) => {
		const trimmed = entry.trim();
		if (isAgentSummary(trimmed)) lastAgentIndex = index;
		if (isOperatorEntry(trimmed)) lastOperatorIndex = index;
	});
	let hiddenAgentCount = 0;
	let hiddenOperatorCount = 0;
	const kept = entries.filter((_entry, index) => {
		const trimmed = _entry.trim();
		if (isAgentSummary(trimmed)) {
			if (index === lastAgentIndex) return true;
			hiddenAgentCount += 1;
			return false;
		}
		if (isOperatorEntry(trimmed)) {
			if (index === lastOperatorIndex) return true;
			hiddenOperatorCount += 1;
			return false;
		}
		return true;
	});
	return {
		text: kept.join("\n\n").trim(),
		hiddenAgentCount,
		hiddenOperatorCount,
	};
}

function CommentsThread({
	issueId,
	source,
}: {
	issueId: number;
	source: string;
}) {
	const scrollRef = useRef<HTMLDivElement>(null);
	const stickToBottomRef = useRef(true);
	const isNearBottom = (el: HTMLDivElement) =>
		el.scrollHeight - el.scrollTop - el.clientHeight < 48;
	// Land on the newest comment when the flyout opens.
	useEffect(() => {
		const el = scrollRef.current;
		if (!el) return;
		el.scrollTop = el.scrollHeight;
		stickToBottomRef.current = true;
	}, [issueId]);
	// When new comments arrive, follow only if the operator was already reading
	// the newest entry. Do not yank someone who scrolled up through history.
	useEffect(() => {
		const el = scrollRef.current;
		if (el && stickToBottomRef.current) el.scrollTop = el.scrollHeight;
	}, [source]);
	const { text, hiddenAgentCount, hiddenOperatorCount } =
		collapseCompletions(source);
	const totalHidden = hiddenAgentCount + hiddenOperatorCount;
	const hasComments = text.trim().length > 0;
	return (
		<div
			ref={scrollRef}
			data-testid="view-comments_md"
			onScroll={(event) => {
				stickToBottomRef.current = isNearBottom(event.currentTarget);
			}}
			className="max-h-[60vh] overflow-y-auto"
		>
			{hasComments ? (
				<div className="space-y-2">
					{totalHidden > 0 && (
						<p
							data-testid="hidden-completions-note"
							className="text-xs text-muted-foreground"
						>
							{hiddenAgentCount > 0 && (
								<>
									{hiddenAgentCount} earlier Symphony completion
									{hiddenAgentCount === 1 ? "" : "s"}
									{hiddenOperatorCount > 0 && ", "}
								</>
							)}
							{hiddenOperatorCount > 0 && (
								<>
									{hiddenOperatorCount} earlier operator repl
									{hiddenOperatorCount === 1 ? "y" : "ies"}
								</>
							)}{" "}
							hidden — see Run history below.
						</p>
					)}
					<div className="rounded-md border p-2">
						<Markdown source={text} />
					</div>
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
	const { panelWidth, isMaximized, startDrag, toggleMaximized } =
		useFlyoutWidth();
	const [tab, setTab] = useState<Tab>("comments");
	const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
	const [stagedDispatch, setStagedDispatch] = useState<StagedDispatchControls>(
		EMPTY_STAGED_DISPATCH,
	);
	const panelRef = useRef<HTMLElement | null>(null);

	const detail = useQuery({
		queryKey: ["issue", issueId],
		queryFn: () => fetchIssue(issueId as number),
		enabled: issueId != null,
		refetchInterval: (query) => issueDetailRefetchIntervalMs(query.state.data),
	});
	const runs = useQuery({
		queryKey: ["runs", issueId],
		queryFn: () => fetchIssueRuns(issueId as number),
		enabled: issueId != null,
		refetchInterval: (query) =>
			runListRefetchIntervalMs(query.state.data) ||
			issueDetailRefetchIntervalMs(detail.data),
	});
	const patch = usePatchIssue();
	const onPatch: OnPatch = (issuePatch) => {
		if (!detail.data) return;
		patch.mutate(
			{ issue: detail.data, patch: issuePatch },
			{
				onSuccess: (data) => {
					if (data.state === "done" || data.state === "archived") {
						onClose();
					}
				},
			},
		);
	};
	// Skill catalog feeds the preferred_skill picker; free text would 422
	// against the FK and silently roll back.
	const skills = useQuery({ queryKey: ["skills"], queryFn: fetchSkills });
	const bindings = useQuery({ queryKey: ["bindings"], queryFn: fetchBindings });
	// Model catalog feeds the preferred_model picker.
	const options = useQuery({
		queryKey: ["issue-options", detail.data?.binding_name ?? ""],
		queryFn: () => fetchIssueOptions(detail.data!.binding_name),
		enabled: detail.data != null,
	});
	const skillNames = (skills.data ?? []).map((s) => s.name);
	const modelOpts = modelOptionsForAgent(
		options.data?.models ?? [],
		detail.data?.preferred_agent ?? null,
	);
	const showEmptySkillHint = skills.isSuccess && skillNames.length === 0;

	// Reset nested flyout state each time a different issue opens. The maximized
	// layout is intentionally not reset; it is the operator's last-used preference.
	useEffect(() => {
		setTab("comments");
		setSelectedRunId(null);
		setStagedDispatch(EMPTY_STAGED_DISPATCH);
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
	const latestRun =
		issue && runs.data
			? (runs.data.find((run) => run.id === issue.latest_run_id) ?? null)
			: null;
	const binding =
		issue && bindings.data
			? (bindings.data.find((item) => item.name === issue.binding_name) ?? null)
			: null;
	const bindingPiMode = binding?.pi_mode ?? null;
	const bindingClaudePersist = binding?.claude_persist ?? null;
	const bindingApprovalEnabled = binding?.approval_enabled ?? false;
	const stageSchedule = (mode: ScheduleMode) => {
		if (!issue) return;
		setStagedDispatch((current) => ({
			...current,
			scheduleMode: mode === scheduleModeFor(issue) ? null : mode,
		}));
	};
	const stageApprovalRequired = (value: boolean) => {
		if (!issue) return;
		setStagedDispatch((current) => ({
			...current,
			approval_required: value === issue.approval_required ? null : value,
		}));
	};
	const stageApproved = (value: boolean) => {
		if (!issue) return;
		setStagedDispatch((current) => ({
			...current,
			approved: value === issue.approved ? null : value,
		}));
	};
	const clearStagedDispatch = () => setStagedDispatch(EMPTY_STAGED_DISPATCH);

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
								modelOptions={modelOpts}
								showEmptySkillHint={showEmptySkillHint}
								onPatch={onPatch}
								staged={stagedDispatch}
								approvalEnabled={bindingApprovalEnabled}
								onStageApprovalRequired={stageApprovalRequired}
								onStageApproved={stageApproved}
								onStageSchedule={stageSchedule}
								stagedPending={false}
							/>

							{patch.isError && (
								<p data-testid="patch-error" className="text-xs text-red-500">
									{(patch.error as { detail?: string } | null)?.detail ||
										"Failed to update — the issue may have changed state. Try again."}
								</p>
							)}

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
											<ReplyComposer
												issue={issue}
												staged={stagedDispatch}
												onClearStaged={clearStagedDispatch}
												onSent={onClose}
											/>
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
												bindingClaudePersist={bindingClaudePersist}
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
