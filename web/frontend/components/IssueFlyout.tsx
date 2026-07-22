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
	issueDetailRefetchIntervalMs,
	runListRefetchIntervalMs,
} from "@/lib/polling";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { RunDetailPanel } from "@/components/RunDetailPanel";
import { OriginChip } from "@/components/badges";
import {
	DEFAULT_SCHEDULE_REASON,
	latestScheduleNotBefore,
} from "@/components/ScheduleControl";
import { RunHistoryList } from "@/components/RunHistoryList";
import { SessionTailPanel } from "@/components/SessionTailPanel";
import { AttachmentPanel } from "@/components/AttachmentPanel";
import { IssueChat } from "@/components/IssueChat";
import { useAppendTailEvent } from "@/components/QueryProvider";
import {
	SlashPickerTextarea,
	type SlashPickerField,
} from "@/components/SlashPickerTextarea";

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
	resolvedDispatchParts,
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
	resolvedDispatchParts: readonly string[];
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
				<OriginChip origin={issue.origin} />
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
				<ChipToggle
					label="hold"
					field="hold"
					value={issue.hold}
					onPatch={onPatch}
				/>
				<ChipText
					label="base"
					field="base_branch"
					value={issue.base_branch}
					onPatch={onPatch}
				/>
			</div>
			{resolvedDispatchParts.length > 0 && (
				<p
					data-testid="resolved-dispatch-hint"
					className="text-xs text-muted-foreground"
				>
					Last run used: {resolvedDispatchParts.join(" · ")}
				</p>
			)}
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

// One composer routes reply/comment/steer from the current issue and run state.
type CommentHint = "note" | "agent-next-park" | "seed";

type ComposerMode =
	| { kind: "reply" }
	| { kind: "comment"; hint: CommentHint }
	| { kind: "steer" };

type ComposerContext = "comments" | "session";

function composerModeFor(
	issue: IssueDetail,
	latestRun: Run | null,
	bindingPiMode: "one-shot" | "rpc" | null,
	bindingClaudePersist: boolean | null,
	freshIssueId: number | null,
	stagedScheduleMode: "next_window" | "none" | null,
): ComposerMode {
	if (stagedScheduleMode != null) return { kind: "comment", hint: "note" };
	const liveRun =
		issue.state === "running" &&
		issue.latest_run_state === "running" &&
		issue.latest_run_id != null;
	const latestRunAgent = latestRun?.agent?.trim().toLowerCase() ?? null;
	const canSteerLive =
		liveRun &&
		((latestRunAgent === "pi" && bindingPiMode === "rpc") ||
			(latestRunAgent === "claude" && bindingClaudePersist === true));
	if (canSteerLive) return { kind: "steer" };
	if (liveRun) return { kind: "comment", hint: "agent-next-park" };
	// Fresh-todo (§10) — just-created issue awaits a first seed comment.
	if (
		freshIssueId === issue.id &&
		issue.state === "todo" &&
		issue.comments_md.trim() === ""
	) {
		return { kind: "comment", hint: "seed" };
	}
	// Scheduled-hold: todo + scheduled_for → comment-note.
	if (issue.state === "todo" && issue.scheduled_for != null)
		return { kind: "comment", hint: "note" };
	// Parked states reply (re-dispatches the agent).
	if (
		issue.state === "in_review" ||
		issue.state === "blocked" ||
		issue.state === "done"
	) {
		return { kind: "reply" };
	}
	// todo without scheduled_for + not fresh — comment-note so the operator
	// can annotate the queued issue without disturbing it.
	return { kind: "comment", hint: "note" };
}

function composerPill(mode: ComposerMode): string {
	switch (mode.kind) {
		case "reply":
			return "Reply · re-dispatches";
		case "steer":
			return "Steer · live";
		case "comment":
			switch (mode.hint) {
				case "note":
					return "Comment · note";
				case "agent-next-park":
					return "Comment · agent sees it next park";
				case "seed":
					return "Comment · seed";
			}
	}
}

function composerPlaceholder(
	mode: ComposerMode,
	hasStaged: boolean,
	latestRunAgent: string | null,
): string {
	if (mode.kind === "steer") {
		return latestRunAgent === "claude"
			? "Queue guidance for Claude’s next turn…"
			: "Redirect the running pi agent…";
	}
	if (mode.kind === "comment" && mode.hint === "agent-next-park") {
		return "Add a comment — agent sees it at its next park…";
	}
	if (mode.kind === "comment" && mode.hint === "seed") {
		return "Seed the new issue with context for the agent…";
	}
	if (hasStaged) {
		return "Comment, then Send to apply staged controls…";
	}
	if (mode.kind === "comment") {
		return "Add a comment (won’t re-run the agent)…";
	}
	return "Write a reply to the agent…";
}

function Composer({
	issue,
	latestRun,
	bindingPiMode,
	bindingClaudePersist,
	staged,
	slashFields,
	onClearStaged,
	onSent,
	context,
	freshIssueId,
}: {
	issue: IssueDetail;
	latestRun: Run | null;
	bindingPiMode: "one-shot" | "rpc" | null;
	bindingClaudePersist: boolean | null;
	staged: StagedDispatchControls;
	slashFields: readonly SlashPickerField[];
	onClearStaged: () => void;
	onSent: () => void;
	context: ComposerContext;
	freshIssueId: number | null;
}) {
	const queryClient = useQueryClient();
	const appendTail = useAppendTailEvent();
	const draftKey = `podium.reply-draft.${issue.id}`;
	const [draft, setDraft] = useState(() => {
		try {
			return window.sessionStorage.getItem(draftKey) ?? "";
		} catch {
			return "";
		}
	});
	const [lastStatus, setLastStatus] = useState<string | null>(null);
	const taRef = useRef<HTMLTextAreaElement>(null);
	const localTailCursorRef = useRef(Date.now());
	const mode = composerModeFor(
		issue,
		latestRun,
		bindingPiMode,
		bindingClaudePersist,
		freshIssueId,
		staged.scheduleMode,
	);
	const latestRunAgent = latestRun?.agent?.trim().toLowerCase() ?? null;
	const isLiveRun =
		issue.state === "running" &&
		issue.latest_run_state === "running" &&
		issue.latest_run_id != null;
	const canSteer =
		isLiveRun &&
		((latestRunAgent === "pi" && bindingPiMode === "rpc") ||
			(latestRunAgent === "claude" && bindingClaudePersist === true));
	const isClaudeRun = isLiveRun && latestRunAgent === "claude";
	const isSteerMode = mode.kind === "steer";
	const hasStaged = hasStagedDispatch(staged);

	const saveDraft = (next: string) => {
		setDraft(next);
		try {
			if (next) {
				window.sessionStorage.setItem(draftKey, next);
			} else {
				window.sessionStorage.removeItem(draftKey);
			}
		} catch {
			// Storage unavailable — keep the in-memory draft.
		}
	};

	// Auto-grow: start small (one row) and expand to fit the draft up to a cap,
	// after which it scrolls. Resync height whenever the draft changes (typing,
	// or the reset to "" after a successful send).
	useEffect(() => {
		const el = taRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${el.scrollHeight}px`;
	}, [draft]);

	// Auto-focus on fresh-todo (§7 fresh-todo case) so the operator can drop a
	// seed comment immediately after creating the issue.
	useEffect(() => {
		if (
			mode.kind === "comment" &&
			mode.hint === "seed" &&
			freshIssueId === issue.id
		) {
			taRef.current?.focus();
		}
	}, [
		mode.kind,
		mode.kind === "comment" ? mode.hint : null,
		freshIssueId,
		issue.id,
	]);

	const inputDisabled = isSteerMode && !canSteer;

	const pill = composerPill(mode);
	const disabledHint =
		mode.kind === "reply"
			? "Reply re-dispatches the agent; type a reply to enable Send."
			: mode.kind === "steer"
				? "Type live guidance to enable Send."
				: mode.hint === "agent-next-park"
					? "Agent is running — your comment is queued for its next park."
					: mode.hint === "seed"
						? "Seed the issue without re-dispatching the agent."
						: "Add a note without re-dispatching the agent.";

	const showReplyDisabledHint =
		context === "comments" && (inputDisabled || draft.trim() === "");
	const showSteerDisabledHint = context === "session" && !canSteer;

	const appendLocalTail = (payload: Record<string, unknown>) => {
		// Optimistic operator events are not file-backed; a monotonic local cursor
		// keeps F3's snapshot-floor dedupe from discarding them.
		const cursor = ++localTailCursorRef.current;
		appendTail({
			issue_id: issue.id,
			run_id: issue.latest_run_id,
			cursor,
			line_cursors: [cursor],
			lines: [JSON.stringify(payload)],
		});
	};
	const invalidateIssue = () => {
		queryClient.invalidateQueries({ queryKey: ["issue", issue.id] });
		queryClient.invalidateQueries({ queryKey: ["issues", issue.binding_name] });
	};

	const send = useMutation({
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
			if (mode.kind === "steer") return postSteer(issue.id, body);
			return mode.kind === "comment"
				? postComment(issue.id, body)
				: postReply(issue.id, body);
		},
		onMutate: (body) => {
			if (mode.kind === "steer") {
				appendLocalTail({ type: "operator_steer", state: "queued", body });
				setLastStatus("Steer queued");
			}
		},
		onSuccess: (_data, body) => {
			saveDraft("");
			onClearStaged();
			if (mode.kind === "steer") {
				appendLocalTail({ type: "operator_steer", state: "delivered", body });
				setLastStatus("Steer delivered");
			} else {
				onSent();
			}
			invalidateIssue();
		},
		onError: (_error, body) => {
			if (mode.kind === "steer") {
				appendLocalTail({ type: "operator_steer", state: "failed", body });
				setLastStatus("Steer failed");
			}
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
	const isPending = send.isPending || abort.isPending;
	const finalSendDisabled =
		inputDisabled || isPending || (!hasStaged && draft.trim() === "");
	const handleSend = () => {
		if (finalSendDisabled) return;
		send.mutate(draft);
	};

	// Tab-localised testids preserve the existing reply and steer contracts.
	const inputTestId = context === "session" ? "steer-input" : "reply-input";
	const sendTestId = context === "session" ? "steer-send" : "reply-send";
	const wrapperTestId = context === "session" ? "steer-composer" : "reply-composer";

	return (
		<div
			className={
				isSteerMode
					? "space-y-2 rounded-md border p-3"
					: "space-y-2"
			}
			data-testid={wrapperTestId}
		>
			<div className="flex items-center justify-between gap-2">
				<div>
					{isSteerMode && (
						<p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
							Live steering
						</p>
					)}
					{showReplyDisabledHint && (
						<p
							data-testid="reply-disabled-hint"
							className="text-xs text-muted-foreground"
						>
							{disabledHint}
						</p>
					)}
					{showSteerDisabledHint && (
						<p
							data-testid="steer-disabled-hint"
							className="text-xs text-muted-foreground"
						>
							{disabledHint}
						</p>
					)}
					{lastStatus && isSteerMode && (
						<p
							data-testid="steer-status"
							className="text-xs text-muted-foreground"
						>
							{lastStatus}
						</p>
					)}
					{isClaudeRun && isSteerMode && (
						<p
							data-testid="steer-agent-copy"
							className="text-xs text-muted-foreground"
						>
							Steer is queued; Claude picks it up at its next turn. Abort:
							interrupt the current turn now (Esc).
						</p>
					)}
				</div>
				{canSteer && (
					<button
						type="button"
						data-testid="steer-abort"
						disabled={isPending}
						onClick={() => abort.mutate()}
						className="rounded-md border border-red-300 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
					>
						Abort
					</button>
				)}
			</div>
			<SlashPickerTextarea
				textareaRef={taRef}
				testid={inputTestId}
				value={draft}
				onChange={saveDraft}
				fields={slashFields}
				onSubmitShortcut={handleSend}
				rows={1}
				placeholder={composerPlaceholder(mode, hasStaged, latestRunAgent)}
				disabled={inputDisabled}
				className="max-h-60 w-full resize-none overflow-y-auto rounded-md border bg-transparent p-2 font-mono text-xs outline-none disabled:opacity-50"
			/>
			{!isSteerMode && send.isError && (
				<p data-testid="reply-error" className="text-xs text-red-500">
					Send failed — the issue may have changed state. Try again.
				</p>
			)}
			{isSteerMode && (send.isError || abort.isError) && (
				<p data-testid="steer-error" className="text-xs text-red-500">
					Steer request failed — the run may have finished or changed agent.
				</p>
			)}
			<div className="flex items-center justify-end gap-2">
				<span className="text-xs text-muted-foreground">⌘/Ctrl + Enter</span>
				<button
					type="button"
					data-testid={sendTestId}
					disabled={finalSendDisabled}
					onClick={handleSend}
					className="rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted/40 disabled:opacity-50"
				>
					<span data-testid="composer-mode-pill">{pill}</span>
				</button>
			</div>
		</div>
	);
}

// Comments thread scroll wrapper. F1 (#33) replaces the raw markdown blob with
// `IssueChat`, which splits on the §2.1 header grammar into per-role bubbles,
// interleaves run bubbles, and renders legacy prose in a collapsed bucket.
function CommentsThread({
	issueId,
	source,
	runs,
}: {
	issueId: number;
	source: string;
	runs: readonly Run[];
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
	return (
		<div
			ref={scrollRef}
			data-testid="view-comments_md"
			onScroll={(event) => {
				stickToBottomRef.current = isNearBottom(event.currentTarget);
			}}
			className="max-h-[60vh] overflow-y-auto pr-1"
		>
			<IssueChat commentsMd={source} runs={runs} />
		</div>
	);
}

// Spec §3 state visibility: a topbar chip carries `state · sublabel` so the
// actionable state (in_review → "your turn") reads at a glance. The chip
// stays in the flyout header above the description card and below the title.
const STATE_SUBLABEL: Record<string, string> = {
	todo: "queued",
	running: "agent working",
	in_review: "your turn",
	blocked: "blocked",
	done: "done",
	archived: "archived",
};

const STATE_CHIP_STYLE: Record<string, string> = {
	todo: "border-slate-300 bg-slate-100 text-slate-800",
	running: "border-sky-300 bg-sky-100 text-sky-800",
	in_review: "border-amber-300 bg-amber-100 text-amber-800",
	blocked: "border-red-300 bg-red-100 text-red-800",
	done: "border-emerald-300 bg-emerald-100 text-emerald-800",
	archived: "border-zinc-300 bg-zinc-100 text-zinc-700",
};

function StateChip({
	state,
	freshTodo,
}: {
	state: string;
	freshTodo: boolean;
}) {
	const sublabel = freshTodo ? "say something" : STATE_SUBLABEL[state] ?? state;
	const style = STATE_CHIP_STYLE[state] ?? "border-slate-300 bg-slate-100 text-slate-800";
	return (
		<span
			data-testid="state-chip"
			data-state={state}
			className={cn(
				"inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
				style,
			)}
		>
			<span className="font-semibold uppercase tracking-wide">{state}</span>
			<span aria-hidden className="opacity-60">·</span>
			<span data-testid="state-chip-sublabel">{sublabel}</span>
		</span>
	);
}

// Freshly-created todo detection for the §3 "say something" sublabel. The
// operator rarely sees a todo that has just been created; the heuristic is
// "todo with no run yet" — matches the §10 fresh-todo case where the composer
// auto-focuses for a seed comment.
function isFreshTodo(issue: IssueDetail): boolean {
	return (
		issue.state === "todo" &&
		issue.latest_run_id == null &&
		issue.comments_md.trim().length === 0
	);
}

const TABS = ["comments", "session", "attachments"] as const;
type Tab = (typeof TABS)[number];

export function IssueFlyout({
	issueId,
	onClose,
	freshIssueId = null,
}: {
	issueId: number | null;
	onClose: () => void;
	freshIssueId?: number | null;
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
	// Per-binding skill catalog (ADR-0033): host-global + this binding's repo.
	const skillBinding = detail.data?.binding_name ?? "";
	const skills = useQuery({
		queryKey: ["skills", skillBinding],
		queryFn: () => fetchSkills(skillBinding || undefined),
		enabled: detail.data != null,
	});
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
	// When the operator left agent/model unset, surface what the latest run
	// actually resolved to (catalog/binding default) so the chips aren't blank.
	const resolvedDispatchParts: string[] = [];
	if (issue && issue.preferred_agent == null && latestRun?.agent) {
		resolvedDispatchParts.push(latestRun.agent);
	}
	if (issue && issue.preferred_model == null && latestRun?.model) {
		resolvedDispatchParts.push(latestRun.model);
	}
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
	const slashFields: SlashPickerField[] = issue
		? [
				{
					id: "state",
					title: "State",
					values: STATE_KEYS.map((value) => ({ value })),
					onSelect: (value) => onPatch({ state: value }),
				},
				{
					id: "skill",
					title: "Skill",
					values: [
						{ value: "", label: "—" },
						...(issue.preferred_skill != null &&
						!skillNames.includes(issue.preferred_skill)
							? [{ value: issue.preferred_skill }]
							: []),
						...skillNames.map((value) => ({ value })),
					],
					onSelect: (value) => onPatch({ preferred_skill: value || null }),
				},
				{
					id: "agent",
					title: "Agent",
					values: [
						{ value: "", label: "—" },
						...(issue.preferred_agent != null &&
						!(options.data?.agents ?? []).includes(issue.preferred_agent)
							? [{ value: issue.preferred_agent }]
							: []),
						...(options.data?.agents ?? []).map((value) => ({ value })),
					],
					onSelect: (value) => onPatch({ preferred_agent: value || null }),
					allowFreeText: true,
				},
				{
					id: "model",
					title: "Model",
					values: [
						{ value: "", label: "—" },
						...(issue.preferred_model != null &&
						!modelOpts.some((option) => option.value === issue.preferred_model)
							? [{ value: issue.preferred_model }]
							: []),
						...modelOpts,
					],
					onSelect: (value) => onPatch({ preferred_model: value || null }),
				},
				{
					id: "effort",
					title: "Effort",
					values: EFFORTS.map((value) => ({ value })),
					onSelect: (value) => onPatch({ reasoning_effort: value }),
				},
				{
					id: "hold",
					title: "Hold",
					values: [
						{ value: "false", label: "off" },
						{ value: "true", label: "active" },
					],
					onSelect: (value) => onPatch({ hold: value === "true" }),
				},
				{
					id: "base",
					title: "Base",
					values: [
						{ value: "", label: "—" },
						...(issue.base_branch != null &&
						!(options.data?.branches ?? []).includes(issue.base_branch)
							? [{ value: issue.base_branch }]
							: []),
						...(options.data?.branches ?? []).map((value) => ({ value })),
					],
					onSelect: (value) => onPatch({ base_branch: value || null }),
					allowFreeText: true,
				},
			]
		: [];
	if (issue?.binding_type === "infra" && bindingApprovalEnabled) {
		slashFields.push(
			{
				id: "approval",
				title: "Approval",
				values: [
					{ value: "false", label: "off" },
					{ value: "true", label: "active" },
				],
				onSelect: (value) => stageApprovalRequired(value === "true"),
			},
			{
				id: "approved",
				title: "Approved",
				values: [
					{ value: "false", label: "off" },
					{ value: "true", label: "active" },
				],
				onSelect: (value) => stageApproved(value === "true"),
			},
		);
	}
	if (issue?.binding_type === "infra") {
		slashFields.push({
			id: "schedule",
			title: "Schedule",
			values: [
				{ value: "none", label: "No" },
				{ value: "next_window", label: "Yes" },
			],
			onSelect: (value) => stageSchedule(value as ScheduleMode),
		});
	}

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
								<div className="min-w-0 space-y-1">
									<p
										className="text-sm text-muted-foreground"
										data-testid="flyout-issue-number"
									>
										Issue #{issue.id}
									</p>
									<h2
										id="flyout-title"
										className="text-lg font-semibold leading-tight"
										data-testid="flyout-title"
									>
										{issue.title}
									</h2>
									<StateChip
										state={issue.state}
										freshTodo={isFreshTodo(issue)}
									/>
								</div>
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

							{/* F4: description renders as a pinned chat-native card at the
                  top of the scroll area. Evolved from the previous
                  muted-Markdown block at the same spot to a bordered card
                  so it reads as a chat message bubble anchoring the thread. */}
							{issue.description && (
								<div
									data-testid="flyout-description-card"
									className="rounded-lg border bg-muted/30 p-3 text-sm"
								>
									<h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
										Description
									</h3>
									<Markdown source={issue.description} />
								</div>
							)}

							<MetadataChips
								issue={issue}
								resolvedDispatchParts={resolvedDispatchParts}
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
										<div className="space-y-3">
											<CommentsThread
												issueId={issue.id}
												source={issue.comments_md}
												runs={runs.data ?? []}
											/>
											<Composer
												key={issue.id}
												issue={issue}
												latestRun={latestRun}
												bindingPiMode={bindingPiMode}
												bindingClaudePersist={bindingClaudePersist}
												staged={stagedDispatch}
												slashFields={slashFields}
												onClearStaged={clearStagedDispatch}
												onSent={onClose}
												context="comments"
												freshIssueId={freshIssueId}
											/>
										</div>
									) : tab === "session" ? (
										<div className="space-y-3">
											<Composer
												key={issue.id}
												issue={issue}
												latestRun={latestRun}
												bindingPiMode={bindingPiMode}
												bindingClaudePersist={bindingClaudePersist}
												staged={stagedDispatch}
												slashFields={slashFields}
												onClearStaged={clearStagedDispatch}
												onSent={onClose}
												context="session"
												freshIssueId={freshIssueId}
											/>
											<SessionTailPanel issueId={issue.id} />
										</div>
									) : (
										<AttachmentPanel issueId={issue.id} />
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
