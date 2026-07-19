"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	createIssue,
	fetchBindings,
	fetchIssueOptions,
	fetchSkills,
	patchIssue,
	uploadAttachment,
	type Issue,
	type IssueCreate,
	type IssueDetail,
	type ModelOption,
} from "@/lib/api";
import {
	ScheduleControl,
	defaultScheduleDraft,
	schedulePayloadFromDraft,
	type ScheduleDraft,
} from "@/components/ScheduleControl";
import { FieldCombobox } from "@/components/FieldCombobox";
import {
	SlashPickerTextarea,
	type SlashPickerField,
} from "@/components/SlashPickerTextarea";

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
				// New-issue modal only creates operator-origin Issues (the API
				// contract doesn't accept origin in IssueCreate; only the
				// spawn/loop fire paths write 'automation' or 'patrol').
				origin: "operator",
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

function modelValue(option: ModelOption, models: readonly ModelOption[]) {
	const duplicateId = models.some(
		(other) => other !== option && other.id === option.id,
	);
	return duplicateId && option.provider
		? `${option.provider}/${option.id}`
		: option.id;
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
	const fileInputRef = useRef<HTMLInputElement | null>(null);
	const queryClient = useQueryClient();

	const [stagedFiles, setStagedFiles] = useState<File[]>([]);
	const [pendingIssue, setPendingIssue] = useState<{
		id: number;
		release: boolean;
	} | null>(null);
	const [uploadError, setUploadError] = useState<string | null>(null);
	const [uploading, setUploading] = useState(false);

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
	const slashFields: SlashPickerField[] = [
		{
			id: "skill",
			title: "Skill",
			values: [{ value: "", label: "—" }, ...skillOptions],
			onSelect: setSkill,
		},
		{
			id: "effort",
			title: "Effort",
			values: [
				{ value: "", label: "— (high)" },
				...effortOptions,
			],
			onSelect: setEffort,
		},
		{
			id: "agent",
			title: "Agent",
			values: [
				{ value: "", label: "— (binding default)" },
				...agentOptions,
			],
			onSelect: setAgent,
			allowFreeText: true,
		},
		{
			id: "model",
			title: "Model",
			values: [
				{ value: "", label: "— (provider default)" },
				...modelOptions,
			],
			onSelect: setModel,
			allowFreeText: true,
		},
		{
			id: "base",
			title: "Base branch",
			values: [
				{ value: "", label: "— (bindings.yml default)" },
				...branchOptions,
			],
			onSelect: setBase,
			allowFreeText: true,
		},
		{
			id: "hold",
			title: "Hold",
			values: [
				{ value: "false", label: "No" },
				{ value: "true", label: "Yes" },
			],
			onSelect: (value) => setHold(value === "true"),
		},
	];
	if (isInfra) {
		slashFields.push({
			id: "schedule",
			title: "Schedule for next maintenance window",
			values: [
				{ value: "none", label: "No" },
				{ value: "next_window", label: "Yes" },
			],
			onSelect: (value) =>
				setScheduleDraft((current) => ({
					...current,
					mode: value === "next_window" ? "next_window" : "none",
				})),
		});
	}

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

	const finishIssue = async (pending: { id: number; release: boolean }) => {
		setUploading(true);
		setUploadError(null);
		const files = stagedFiles;
		const failed: File[] = [];
		for (const file of files) {
			try {
				await uploadAttachment(pending.id, file);
				queryClient.invalidateQueries({
					queryKey: ["attachments", pending.id],
				});
			} catch {
				failed.push(file);
			}
		}
		setStagedFiles((current) =>
			current.filter((file) => !files.includes(file) || failed.includes(file)),
		);
		queryClient.invalidateQueries({ queryKey: ["issues", binding] });
		if (failed.length > 0) {
			setUploadError(
				`${failed.length} attachment(s) failed: ${failed.map((file) => file.name).join(", ")}`,
			);
			setUploading(false);
			return;
		}
		if (pending.release) {
			try {
				await patchIssue(pending.id, { hold: false });
				queryClient.invalidateQueries({ queryKey: ["issues", binding] });
			} catch {
				setUploadError(
					"Attachments uploaded, but failed to release issue — try again.",
				);
				setUploading(false);
				return;
			}
		}
		setUploading(false);
		onClose();
	};

	const handlePostCreate = (row: IssueDetail, release: boolean) => {
		const pending = { id: row.id, release };
		setPendingIssue(pending);
		void finishIssue(pending);
	};

	const submit = (e: React.FormEvent) => {
		e.preventDefault();
		const trimmed = description.trim();
		if (!trimmed || create.isPending || uploading) return;
		if (pendingIssue) {
			void finishIssue(pendingIssue);
			return;
		}
		const schedule = isInfra ? schedulePayloadFromDraft(scheduleDraft) : null;
		const hasFiles = stagedFiles.length > 0;
		create.mutate(
			{
				description: trimmed,
				...(skill && { preferred_skill: skill }),
				...(agent.trim() && { preferred_agent: agent.trim() }),
				...(model.trim() && { preferred_model: model.trim() }),
				...(effort && { reasoning_effort: effort }),
				...(schedule && { schedule }),
				...(base.trim() && { base_branch: base.trim() }),
				...((hold || hasFiles) && { hold: true }),
			},
			{
				onSuccess: (row) => handlePostCreate(row, hasFiles && !hold),
			},
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
						<SlashPickerTextarea
							testid="new-issue-description"
							value={description}
							onChange={setDescription}
							fields={slashFields}
							rows={4}
							autoFocus
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

					{/* File staging — upload happens after issue creation */}
					<div className="space-y-1">
						<span className="text-xs font-medium text-muted-foreground">
							Attachments
						</span>
						<input
							ref={fileInputRef}
							type="file"
							multiple
							disabled={create.isPending || uploading}
							data-testid="new-issue-file-input"
							className="sr-only"
							onChange={(e) => {
								const files = Array.from(e.target.files ?? []);
								if (files.length > 0) {
									setStagedFiles((prev) => [...prev, ...files]);
									setUploadError(null);
								}
								if (fileInputRef.current) fileInputRef.current.value = "";
							}}
						/>
						<button
							type="button"
							disabled={create.isPending || uploading}
							data-testid="new-issue-file-pick"
							onClick={() => fileInputRef.current?.click()}
							className="rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted/40"
						>
							Choose files
						</button>
						{stagedFiles.length > 0 && (
							<ul className="space-y-1" data-testid="new-issue-staged-files">
								{stagedFiles.map((file, i) => (
									<li
										key={`${file.name}-${i}`}
										className="flex items-center gap-2 text-xs"
									>
										<span className="flex-1 truncate">{file.name}</span>
										<button
											type="button"
											disabled={create.isPending || uploading}
											data-testid="new-issue-file-remove"
											onClick={() =>
												setStagedFiles((prev) => prev.filter((_, j) => j !== i))
											}
											className="text-muted-foreground hover:text-foreground"
										>
											×
										</button>
									</li>
								))}
							</ul>
						)}
					</div>

					{create.isError && (
						<p data-testid="new-issue-error" className="text-xs text-red-500">
							Failed to create issue — check the API and try again.
						</p>
					)}
					{uploadError && (
						<p
							data-testid="new-issue-upload-error"
							className="text-xs text-red-500"
						>
							{uploadError}
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
							disabled={!description.trim() || create.isPending || uploading}
							className="rounded-md border bg-foreground px-3 py-1.5 text-sm font-medium text-background transition disabled:opacity-40"
						>
							{uploading ? "Uploading…" : pendingIssue ? "Retry" : "Create"}
						</button>
					</div>
				</form>
			</div>
		</>
	);
}
