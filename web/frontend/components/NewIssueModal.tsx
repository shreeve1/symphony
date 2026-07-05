"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	createIssue,
	fetchBindings,
	fetchIssueOptions,
	fetchSkills,
	type Issue,
	type IssueCreate,
	type ModelOption,
} from "@/lib/api";
import {
	ScheduleControl,
	defaultScheduleDraft,
	schedulePayloadFromDraft,
	type ScheduleDraft,
} from "@/components/ScheduleControl";

// Fallback effort list for models that don't declare an `efforts` set in the
// catalog. Models that do (e.g. gpt-5.5) drive the dropdown from their own set
// so the operator can't pick an effort the model will reject at dispatch.
const DEFAULT_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh"];

// Optimistic create (#014): prepend a temp card to the board cache on submit,
// swap it for the canonical server row on success, roll back on error, and
// refetch once the write settles. The canonical row is the full detail shape
// (a superset of Issue), so the list cache transiently holds one wider row
// until the settle-refetch trims it — harmless, extra fields are ignored.
function useCreateIssue(binding: string, bindingType: Issue["binding_type"]) {
	const queryClient = useQueryClient();
	const key = ["issues", binding];
	return useMutation({
		mutationFn: (body: IssueCreate) => createIssue(binding, body),
		onMutate: async (body) => {
			await queryClient.cancelQueries({ queryKey: key });
			const previous = queryClient.getQueryData<Issue[]>(key);
			const tempId = -Date.now(); // negative: cannot collide with a server-assigned id
			const temp: Issue = {
				id: tempId,
				binding_name: binding,
				binding_type: bindingType,
				title: "Generating title...",
				description: body.description ?? null,
				state: "todo",
				priority: body.priority ?? null,
				preferred_agent: body.preferred_agent ?? null,
				preferred_model: body.preferred_model ?? null,
				preferred_skill: body.preferred_skill ?? null,
				reasoning_effort: body.reasoning_effort ?? "high",
				worktree_active: body.worktree_active ?? false,
				hold: body.hold ?? false,
				approval_required: body.approval_required ?? false,
				approved: body.approved ?? false,
				scheduled_for: body.schedule ? new Date().toISOString() : null,
				worktree_path: "",
				worktree_branch: "",
				base_branch: body.base_branch ?? null,
				created_at: null,
				updated_at: null,
				latest_run_id: null,
				latest_verdict: null,
				latest_run_state: null,
				last_event_at: null,
				blocked_by: body.blocked_by ?? [],
				locks: body.locks ?? [],
				dependencies_satisfied: true,
				unsatisfied_blocked_by: [],
				lock_conflicts: [],
			};
			queryClient.setQueryData<Issue[]>(key, (old) => [temp, ...(old ?? [])]);
			return { previous, tempId: temp.id };
		},
		onSuccess: (row, _body, context) => {
			queryClient.setQueryData<Issue[]>(key, (old) => {
				const replaced = (old ?? []).map((issue) =>
					issue.id === context.tempId ? row : issue,
				);
				return replaced.filter(
					(issue, index) =>
						replaced.findIndex((candidate) => candidate.id === issue.id) ===
						index,
				);
			});
		},
		onError: (_error, _body, context) => {
			if (context?.previous) queryClient.setQueryData(key, context.previous);
		},
		onSettled: () => {
			queryClient.invalidateQueries({ queryKey: key });
		},
	});
}

export function NewIssueButton({ binding }: { binding: string }) {
	const [open, setOpen] = useState(false);
	return (
		<>
			<button
				type="button"
				data-testid="new-issue-button"
				onClick={() => setOpen(true)}
				className="rounded-md border px-3 py-1.5 text-sm font-medium transition hover:border-foreground/30 hover:shadow"
			>
				+ New Issue
			</button>
			{open && (
				<NewIssueModal binding={binding} onClose={() => setOpen(false)} />
			)}
		</>
	);
}

type ComboOption = { value: string; label?: string };

function labelFor(options: readonly ComboOption[], value: string) {
	return options.find((option) => option.value === value)?.label ?? value;
}

function modelValue(option: ModelOption, models: readonly ModelOption[]) {
	const duplicateId = models.some(
		(other) => other !== option && other.id === option.id,
	);
	return duplicateId && option.provider
		? `${option.provider}/${option.id}`
		: option.id;
}

// Searchable zero-dependency combobox. Free-text mode updates the submitted
// value as the operator types; selection-only mode only submits clicked options.
function FieldCombobox({
	label,
	testid,
	value,
	onChange,
	options,
	emptyHint,
	allowFreeText = false,
}: {
	label: string;
	testid: string;
	value: string;
	onChange: (value: string) => void;
	options: readonly ComboOption[];
	emptyHint?: string;
	allowFreeText?: boolean;
}) {
	const [open, setOpen] = useState(false);
	const [draft, setDraft] = useState(labelFor(options, value));
	const [activeIndex, setActiveIndex] = useState(-1);
	const listRef = useRef<HTMLDivElement | null>(null);
	const listId = `${testid}-listbox`;
	const normalizedDraft = draft.trim().toLowerCase();
	// A draft that still mirrors the selected value (e.g. the preselected
	// default model) is not a search: show the full list until the operator
	// actually types.
	const filterActive =
		normalizedDraft !== labelFor(options, value).trim().toLowerCase();
	const filtered = options.filter((option) => {
		const label = option.label ?? option.value;
		return (
			!filterActive ||
			!normalizedDraft ||
			label.toLowerCase().includes(normalizedDraft) ||
			option.value.toLowerCase().includes(normalizedDraft)
		);
	});

	// Selectable rows shown in the popup: leading empty option + filtered list.
	const emptyLabel = emptyHint ? `— (${emptyHint})` : "—";
	const entries: ComboOption[] = [
		{ value: "", label: emptyLabel },
		...filtered,
	];

	useEffect(() => {
		setDraft(labelFor(options, value));
	}, [options, value]);

	// Reset the highlight whenever the popup reopens or the visible list changes.
	useEffect(() => {
		setActiveIndex(-1);
	}, [open, normalizedDraft]);

	// Keep the highlighted row scrolled into view as arrow keys move it.
	useEffect(() => {
		if (!open || activeIndex < 0) return;
		listRef.current
			?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
			?.scrollIntoView({ block: "nearest" });
	}, [open, activeIndex]);

	const choose = (next: string) => {
		onChange(next);
		setDraft(labelFor(options, next));
		setOpen(false);
		setActiveIndex(-1);
	};

	const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "ArrowDown") {
			e.preventDefault();
			if (!open) setOpen(true);
			else setActiveIndex((i) => Math.min(i + 1, entries.length - 1));
		} else if (e.key === "ArrowUp") {
			e.preventDefault();
			if (!open) setOpen(true);
			else setActiveIndex((i) => Math.max(i - 1, 0));
		} else if (e.key === "Enter") {
			if (open && activeIndex >= 0 && activeIndex < entries.length) {
				e.preventDefault();
				choose(entries[activeIndex].value);
			}
		} else if (e.key === "Escape" && open) {
			// Close only the popup; stop the modal's window-level Escape handler.
			e.preventDefault();
			e.stopPropagation();
			setOpen(false);
			setActiveIndex(-1);
			if (!allowFreeText) setDraft(labelFor(options, value));
		}
	};

	return (
		<label className="relative block flex-1 space-y-1">
			<span className="text-xs font-medium text-muted-foreground">{label}</span>
			<input
				data-testid={testid}
				role="combobox"
				aria-expanded={open}
				aria-controls={listId}
				aria-autocomplete="list"
				aria-activedescendant={
					open && activeIndex >= 0
						? `${testid}-option-${activeIndex}`
						: undefined
				}
				value={draft}
				placeholder={emptyLabel}
				onFocus={() => setOpen(true)}
				onKeyDown={onKeyDown}
				onChange={(e) => {
					setDraft(e.target.value);
					setOpen(true);
					if (allowFreeText) onChange(e.target.value);
					if (!allowFreeText && e.target.value === "") onChange("");
				}}
				onBlur={() => {
					setOpen(false);
					if (!allowFreeText) setDraft(labelFor(options, value));
				}}
				className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
			/>
			{open && (
				<div
					ref={listRef}
					id={listId}
					role="listbox"
					className="absolute z-50 mt-1 max-h-44 w-full overflow-auto rounded-md border bg-background p-1 shadow-lg"
				>
					{entries.map((option, index) => {
						const active = index === activeIndex;
						const isEmpty = option.value === "";
						return (
							<button
								type="button"
								key={option.value || "__empty__"}
								id={`${testid}-option-${index}`}
								data-index={index}
								data-testid={`${testid}-option`}
								role="option"
								aria-selected={active}
								onMouseEnter={() => setActiveIndex(index)}
								onMouseDown={(e) => e.preventDefault()}
								onClick={() => choose(option.value)}
								className={`block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-muted ${
									isEmpty ? "text-muted-foreground" : ""
								} ${active ? "bg-muted" : ""}`}
							>
								{option.label ?? option.value}
							</button>
						);
					})}
					{filtered.length === 0 && (
						<div className="px-2 py-1.5 text-sm text-muted-foreground">
							No matches
						</div>
					)}
				</div>
			)}
		</label>
	);
}

function NewIssueModal({
	binding,
	onClose,
}: {
	binding: string;
	onClose: () => void;
}) {
	const [description, setDescription] = useState("");
	const [skill, setSkill] = useState("");
	const [agent, setAgent] = useState("");
	const [model, setModel] = useState("");
	const [effort, setEffort] = useState("");
	const [base, setBase] = useState("");
	const [hold, setHold] = useState(false);
	const [scheduleDraft, setScheduleDraft] =
		useState<ScheduleDraft>(defaultScheduleDraft);
	const descRef = useRef<HTMLTextAreaElement | null>(null);

	const bindings = useQuery({ queryKey: ["bindings"], queryFn: fetchBindings });
	const bindingType =
		bindings.data?.find((item) => item.name === binding)?.binding_type ??
		"coding";
	const isInfra = bindingType === "infra";
	const create = useCreateIssue(binding, bindingType);
	// Per-binding skill catalog (ADR-0033): host-global + this binding's repo.
	const skills = useQuery({
		queryKey: ["skills", binding],
		queryFn: () => fetchSkills(binding),
	});
	// Agent/model/branch dropdown choices (branches read live from the repo).
	const options = useQuery({
		queryKey: ["issue-options", binding],
		queryFn: () => fetchIssueOptions(binding),
	});
	const skillNames = (skills.data ?? []).map((s) => s.name);
	const skillOptions = skillNames.map((name) => ({ value: name }));
	const agentOptions = (options.data?.agents ?? []).map((name) => ({
		value: name,
	}));
	const models = options.data?.models ?? [];
	const modelOptions = models
		.filter((option: ModelOption) => !agent || option.agent === agent)
		.map((option: ModelOption) => {
			const value = modelValue(option, models);
			return {
				value,
				label: option.label ? `${option.label} (${value})` : value,
			};
		});
	const branchOptions = (options.data?.branches ?? []).map((name) => ({
		value: name,
	}));
	const selectedModelEfforts = models.find(
		(option: ModelOption) => modelValue(option, models) === model,
	)?.efforts;
	const effortChoices = selectedModelEfforts ?? DEFAULT_EFFORTS;
	const effortOptions = effortChoices.map((name) => ({ value: name }));
	const showEmptySkillHint = skills.isSuccess && skillNames.length === 0;

	useEffect(() => descRef.current?.focus(), []);

	// Agent-aware default preselect (#045): when agent changes or options
	// load, preselect the default:true model whose agent matches the selected
	// agent. If the selected agent has no default, clear the model field so
	// the operator never silently submits a cross-agent mismatch.
	useEffect(() => {
		const match = models.find(
			(option: ModelOption) => option.default && option.agent === agent,
		);
		setModel(match ? modelValue(match, models) : "");
	}, [models, agent]);

	// Clear a set effort the newly selected model doesn't support, so the form
	// never submits an effort the dispatch gate would reject.
	useEffect(() => {
		if (effort && !effortChoices.includes(effort)) setEffort("");
	}, [effort, effortChoices]);

	useEffect(() => {
		const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [onClose]);

	const submit = (e: React.FormEvent) => {
		e.preventDefault();
		const trimmed = description.trim();
		if (!trimmed || create.isPending) return;
		// The optimistic card carries the board UI immediately, but the modal only
		// closes on success: on failure the temp card silently rolls back, so the
		// still-open modal (typed values intact + error line) is the only place
		// the operator learns the create didn't land.
		// Only send what the operator set; omitted keys take server defaults.
		const schedule = isInfra ? schedulePayloadFromDraft(scheduleDraft) : null;
		create.mutate(
			{
				description: trimmed,
				...(skill && { preferred_skill: skill }),
				...(agent.trim() && { preferred_agent: agent.trim() }),
				...(model.trim() && { preferred_model: model.trim() }),
				...(effort && { reasoning_effort: effort }),
				...(schedule && { schedule }),
				...(base.trim() && { base_branch: base.trim() }),
				...(hold && { hold: true }),
			},
			{ onSuccess: onClose },
		);
	};

	return (
		<>
			<div
				data-testid="new-issue-backdrop"
				className="fixed inset-0 z-40 bg-black/20"
				onClick={onClose}
			/>
			<div
				data-testid="new-issue-modal"
				role="dialog"
				aria-modal="true"
				aria-labelledby="new-issue-heading"
				className="fixed left-1/2 top-1/2 z-50 w-[28rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-5 shadow-xl"
			>
				<h2 id="new-issue-heading" className="mb-4 text-lg font-semibold">
					New issue
				</h2>
				<form onSubmit={submit} className="space-y-3">
					<label className="block space-y-1">
						<span className="text-xs font-medium text-muted-foreground">
							Description
						</span>
						<textarea
							ref={descRef}
							data-testid="new-issue-description"
							value={description}
							rows={4}
							onChange={(e) => setDescription(e.target.value)}
							className="w-full rounded-md border bg-transparent px-2 py-1.5 font-mono text-xs outline-none focus:border-foreground/40"
						/>
					</label>

					<div className="flex gap-3">
						<FieldCombobox
							label="Skill"
							testid="new-issue-skill"
							value={skill}
							onChange={setSkill}
							options={skillOptions}
						/>
						<FieldCombobox
							label="Effort"
							testid="new-issue-effort"
							value={effort}
							onChange={setEffort}
							options={effortOptions}
							emptyHint="high"
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

					<div className="flex gap-3">
						<FieldCombobox
							label="Agent"
							testid="new-issue-agent"
							value={agent}
							onChange={setAgent}
							options={agentOptions}
							emptyHint="binding default"
							allowFreeText
						/>
						<FieldCombobox
							label="Model"
							testid="new-issue-model"
							value={model}
							onChange={setModel}
							options={modelOptions}
							emptyHint="provider default"
							allowFreeText
						/>
					</div>

					<div className="flex gap-3">
						<FieldCombobox
							label="Base branch"
							testid="new-issue-base"
							value={base}
							onChange={setBase}
							options={branchOptions}
							emptyHint="bindings.yml default"
							allowFreeText
						/>
					</div>

					{isInfra && (
						<ScheduleControl
							testid="new-issue-schedule"
							draft={scheduleDraft}
							onChange={setScheduleDraft}
						/>
					)}

					<label className="flex items-center gap-2 text-xs text-muted-foreground">
						<input
							type="checkbox"
							data-testid="new-issue-hold"
							checked={hold}
							onChange={(e) => setHold(e.target.checked)}
							className="h-3.5 w-3.5"
						/>
						Hold (don't dispatch)
					</label>

					{create.isError && (
						<p data-testid="new-issue-error" className="text-xs text-red-500">
							Failed to create issue — check the API and try again.
						</p>
					)}

					<div className="flex justify-end gap-2 pt-1">
						<button
							type="button"
							onClick={onClose}
							className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
						>
							Cancel
						</button>
						<button
							type="submit"
							data-testid="new-issue-submit"
							disabled={!description.trim() || create.isPending}
							className="rounded-md border bg-foreground px-3 py-1.5 text-sm font-medium text-background transition disabled:opacity-40"
						>
							Create
						</button>
					</div>
				</form>
			</div>
		</>
	);
}
