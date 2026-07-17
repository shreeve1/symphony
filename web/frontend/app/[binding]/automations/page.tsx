"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	fetchAutomations,
	createAutomation,
	updateAutomation,
	deleteAutomation,
	fetchBindings,
	fetchIssueOptions,
	fetchSkills,
	type Automation,
	type AutomationCreate,
	type AutomationPatch,
	type ModelOption,
} from "@/lib/api";
import { formatAge } from "@/lib/issues";
import { FieldCombobox } from "@/components/FieldCombobox";

// Fallback effort list for models that don't declare an `efforts` set in the
// catalog (mirrors NewIssueModal), so the operator can't pin an effort the
// model will reject at fire-time.
const DEFAULT_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh"];

function modelValue(option: ModelOption): string {
	return option.provider ? `${option.provider}/${option.id}` : option.id;
}

function countLabel(a: Automation): string {
	if (a.mode === "loop") {
		return a.loop_iteration_cap == null
			? "Unlimited"
			: `Cap ${a.loop_iteration_cap}`;
	}
	if (a.spawn_run_count == null) return "Unlimited";
	return `${Math.max(0, a.spawn_run_count - a.occurrences_fired)} left`;
}

function nextLabel(a: Automation): string {
	if (a.next_fire_at) return formatAge(a.next_fire_at);
	if (a.mode === "loop") return "per completion";
	return "—";
}

export default function AutomationsPage() {
	const { binding } = useParams<{ binding: string }>();
	const queryClient = useQueryClient();

	const [showForm, setShowForm] = useState(false);
	const [editing, setEditing] = useState<Automation | null>(null);

	// Form state
	const [mode, setMode] = useState<"spawn" | "loop">("spawn");
	const [title, setTitle] = useState("");
	const [body, setBody] = useState("");
	const [intervalSec, setIntervalSec] = useState("");
	const [runCount, setRunCount] = useState("");
	const [iterCap, setIterCap] = useState("");
	const [marker, setMarker] = useState("DONE.md");
	// Per-Issue dispatch pins (issue #459). Each empty-string defaults to
	// the binding-level default at fire-time (model/skill/agent from the
	// model catalog, base_branch from bindings.yml, worktree_active from
	// bindings.yml/worktree_default).
	const [preferredSkill, setPreferredSkill] = useState("");
	const [preferredAgent, setPreferredAgent] = useState("");
	const [preferredModel, setPreferredModel] = useState("");
	const [reasoningEffort, setReasoningEffort] = useState("");
	const [baseBranch, setBaseBranch] = useState("");
	const [worktreeActive, setWorktreeActive] = useState(false);

	const { data: bindings } = useQuery({
		queryKey: ["bindings"],
		queryFn: fetchBindings,
	});
	const bindingType =
		bindings?.find((b) => b.name === binding)?.binding_type ?? "coding";
	const isInfra = bindingType === "infra";

	const { data: automations, isLoading } = useQuery({
		queryKey: ["automations", binding],
		queryFn: () => fetchAutomations(binding),
		enabled: Boolean(binding),
	});

	// Issue #461: same skill catalog + agent/model options the New Issue modal
	// uses, so the automations form can offer a typed combobox instead of
	// free-text inputs that fail at dispatch when the operator typoes.
	const { data: pinSkills } = useQuery({
		queryKey: ["skills", binding],
		queryFn: () => fetchSkills(binding),
		enabled: Boolean(binding),
	});
	const { data: pinOptions } = useQuery({
		queryKey: ["issue-options", binding],
		queryFn: () => fetchIssueOptions(binding),
		enabled: Boolean(binding),
	});
	const pinSkillNames = (pinSkills ?? []).map((s) => s.name);
	const pinSkillOptions = pinSkillNames.map((name) => ({
		value: name,
		label: name,
	}));
	const showEmptySkillHint = Boolean(pinSkills) && pinSkillNames.length === 0;
	const pinAgentOptions = (pinOptions?.agents ?? []).map((name) => ({
		value: name,
		label: name,
	}));
	const pinModels = pinOptions?.models ?? [];
	// Filter models to the selected agent so the operator can't pin a
	// cross-agent model combo that resolve_model rejects at fire-time
	// (model_catalog.ModelResolutionError). No agent picked = show all.
	const pinModelOptions = pinModels
		.filter((option) => !preferredAgent || option.agent === preferredAgent)
		.map((option) => ({
			value: modelValue(option),
			label: option.label ?? option.id,
		}));
	// Drive the effort list from the selected model's declared set, so the
	// operator can't pin an effort the model rejects at dispatch.
	const selectedModelEfforts = pinModels.find(
		(option) => modelValue(option) === preferredModel,
	)?.efforts;
	const effortChoices = selectedModelEfforts ?? DEFAULT_EFFORTS;

	// Clear a pinned model that doesn't belong to the newly selected agent, so
	// the form never persists a cross-agent mismatch. Empty stays empty.
	useEffect(() => {
		if (!preferredModel || !preferredAgent) return;
		const match = pinModels.find(
			(option) => modelValue(option) === preferredModel,
		);
		if (match && match.agent !== preferredAgent) setPreferredModel("");
	}, [preferredAgent, preferredModel, pinModels]);

	// Clear a pinned effort the selected model doesn't support.
	useEffect(() => {
		if (reasoningEffort && !effortChoices.includes(reasoningEffort))
			setReasoningEffort("");
	}, [reasoningEffort, effortChoices]);

	const createMut = useMutation({
		mutationFn: (body: AutomationCreate) => createAutomation(binding, body),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["automations", binding] });
			resetForm();
		},
	});

	const updateMut = useMutation({
		mutationFn: ({ id, patch }: { id: number; patch: AutomationPatch }) =>
			updateAutomation(binding, id, patch),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["automations", binding] });
			resetForm();
		},
	});

	const toggleMut = useMutation({
		mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
			updateAutomation(binding, id, { enabled }),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["automations", binding] });
		},
	});

	const deleteMut = useMutation({
		mutationFn: (id: number) => deleteAutomation(binding, id),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["automations", binding] });
		},
	});

	const resetForm = () => {
		setShowForm(false);
		setEditing(null);
		setMode("spawn");
		setTitle("");
		setBody("");
		setIntervalSec("");
		setRunCount("");
		setIterCap("");
		setMarker("DONE.md");
		setPreferredSkill("");
		setPreferredAgent("");
		setPreferredModel("");
		setReasoningEffort("");
		setBaseBranch("");
		setWorktreeActive(false);
	};

	const openEdit = (a: Automation) => {
		setEditing(a);
		setMode(a.mode);
		setTitle(a.template_title);
		setBody(a.template_body);
		setIntervalSec(a.spawn_interval_seconds?.toString() ?? "");
		setRunCount(a.spawn_run_count?.toString() ?? "");
		setIterCap(a.loop_iteration_cap?.toString() ?? "");
		setMarker(a.loop_completion_marker);
		setPreferredSkill(a.preferred_skill ?? "");
		setPreferredAgent(a.preferred_agent ?? "");
		setPreferredModel(a.preferred_model ?? "");
		setReasoningEffort(a.reasoning_effort ?? "");
		setBaseBranch(a.base_branch ?? "");
		setWorktreeActive(a.worktree_active);
		setShowForm(true);
	};

	const submit = (e: React.FormEvent) => {
		e.preventDefault();
		if (!title.trim()) return;
		const payload: AutomationCreate = {
			mode: isInfra ? "spawn" : mode,
			template_title: title.trim(),
			template_body: body.trim(),
		};
		if (mode === "spawn") {
			const secs = parseInt(intervalSec, 10);
			if (!isNaN(secs) && secs > 0) payload.spawn_interval_seconds = secs;
			payload.spawn_run_count = runCount.trim() ? parseInt(runCount, 10) : null;
		} else {
			const cap = parseInt(iterCap, 10);
			if (!isNaN(cap) && cap > 0) payload.loop_iteration_cap = cap;
			payload.loop_completion_marker = marker.trim() || "DONE.md";
		}
		// Per-Issue pin fields (issue #459). Empty-string omitted so the API
		// keeps them NULL and the fire path applies the binding default.
		if (preferredSkill.trim()) payload.preferred_skill = preferredSkill.trim();
		if (preferredAgent.trim()) payload.preferred_agent = preferredAgent.trim();
		if (preferredModel.trim()) payload.preferred_model = preferredModel.trim();
		if (reasoningEffort.trim())
			payload.reasoning_effort = reasoningEffort.trim();
		if (baseBranch.trim()) payload.base_branch = baseBranch.trim();
		// For loop mode, worktree_active is forced True at fire-time regardless
		// of this checkbox (loops require a persistent worktree, Q4 of #459).
		// Send true explicitly so the API distinguishes a confirmed loop
		// from a default-False that the validation gate would reject
		// (issue #461). For spawn mode, this is the actual override.
		if (mode === "spawn") {
			payload.worktree_active = worktreeActive;
		} else if (mode === "loop") {
			payload.worktree_active = true;
		}
		if (editing) {
			const { mode: _mode, ...patch } = payload;
			updateMut.mutate({ id: editing.id, patch });
		} else {
			createMut.mutate(payload);
		}
	};

	const handleModeChange = (m: "spawn" | "loop") => {
		// For infra, lock to spawn only.
		if (isInfra) return;
		setMode(m);
	};

	return (
		<div data-testid="automations-page" className="flex h-full flex-col gap-4">
			<div className="flex items-center justify-between">
				<h2 className="text-2xl font-semibold tracking-tight">Automations</h2>
				<button
					type="button"
					data-testid="automation-create-btn"
					onClick={() => {
						resetForm();
						setShowForm(true);
					}}
					className="rounded-md border px-3 py-1.5 text-sm font-medium transition hover:border-foreground/30 hover:shadow"
				>
					+ Create
				</button>
			</div>

			{/* Create/Edit form */}
			{showForm && (
				<div
					data-testid="automation-form"
					className="rounded-md border p-4 space-y-3"
				>
					<h3 className="text-sm font-semibold">
						{editing ? "Edit" : "New"} automation
					</h3>
					<form onSubmit={submit} className="space-y-3">
						<label className="block space-y-1">
							<span className="text-xs font-medium text-muted-foreground">
								Mode
							</span>
							<select
								data-testid="automation-form-mode"
								value={mode}
								disabled={Boolean(editing)}
								onChange={(e) =>
									handleModeChange(e.target.value as "spawn" | "loop")
								}
								className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
							>
								<option value="spawn">Spawn</option>
								{!isInfra && <option value="loop">Loop</option>}
							</select>
						</label>

						<label className="block space-y-1">
							<span className="text-xs font-medium text-muted-foreground">
								Template title
							</span>
							<input
								data-testid="automation-form-title"
								value={title}
								required
								onChange={(e) => setTitle(e.target.value)}
								className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
							/>
						</label>

						<label className="block space-y-1">
							<span className="text-xs font-medium text-muted-foreground">
								Template body
							</span>
							<textarea
								data-testid="automation-form-body"
								value={body}
								required
								rows={3}
								onChange={(e) => setBody(e.target.value)}
								className="w-full rounded-md border bg-transparent px-2 py-1.5 font-mono text-xs outline-none focus:border-foreground/40"
							/>
						</label>

						{mode === "spawn" && (
							<div className="flex gap-3">
								<label className="block flex-1 space-y-1">
									<span className="text-xs font-medium text-muted-foreground">
										Interval (seconds)
									</span>
									<input
										data-testid="automation-form-interval"
										type="number"
										min="1"
										required
										value={intervalSec}
										onChange={(e) => setIntervalSec(e.target.value)}
										className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
									/>
								</label>
								<label className="block flex-1 space-y-1">
									<span className="text-xs font-medium text-muted-foreground">
										Max runs (empty = unlimited)
									</span>
									<input
										data-testid="automation-form-count"
										type="number"
										min="1"
										value={runCount}
										onChange={(e) => setRunCount(e.target.value)}
										className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
									/>
								</label>
							</div>
						)}

						{mode === "loop" && !isInfra && (
							<div className="flex gap-3">
								<label className="block flex-1 space-y-1">
									<span className="text-xs font-medium text-muted-foreground">
										Iteration cap
									</span>
									<input
										data-testid="automation-form-iter-cap"
										type="number"
										min="1"
										required
										value={iterCap}
										onChange={(e) => setIterCap(e.target.value)}
										className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
									/>
								</label>
								<label className="block flex-1 space-y-1">
									<span className="text-xs font-medium text-muted-foreground">
										Completion marker
									</span>
									<input
										data-testid="automation-form-marker"
										value={marker}
										onChange={(e) => setMarker(e.target.value)}
										className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
									/>
								</label>
							</div>
						)}

						{/* Per-Issue dispatch pins (issues #459/#461/#462). Rendered
						    inline and front-and-center; every field is optional and
						    falls back to the binding default at fire-time when empty. */}
						<div
							data-testid="automation-form-pins"
							className="space-y-3 rounded-md border p-3"
						>
							<div className="flex gap-3">
								<FieldCombobox
									label="Skill"
									testid="automation-form-pin-skill"
									value={preferredSkill}
									onChange={setPreferredSkill}
									options={pinSkillOptions}
									emptyHint="binding default"
								/>
								<label className="block flex-1 space-y-1">
									<span className="text-xs font-medium text-muted-foreground">
										Effort
									</span>
									<select
										data-testid="automation-form-pin-effort"
										value={reasoningEffort}
										onChange={(e) => setReasoningEffort(e.target.value)}
										className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
									>
										<option value="">(binding default)</option>
										{effortChoices.map((name) => (
											<option key={name} value={name}>
												{name}
											</option>
										))}
									</select>
								</label>
							</div>
							<div className="flex gap-3">
								<FieldCombobox
									label="Agent"
									testid="automation-form-pin-agent"
									value={preferredAgent}
									onChange={setPreferredAgent}
									options={pinAgentOptions}
									emptyHint="binding default"
								/>
								<FieldCombobox
									label="Model"
									testid="automation-form-pin-model"
									value={preferredModel}
									onChange={setPreferredModel}
									options={pinModelOptions}
									emptyHint="binding default"
								/>
							</div>
							{showEmptySkillHint && (
								<p
									data-testid="automation-skill-catalog-empty"
									className="text-xs text-muted-foreground"
								>
									Run `podium skills refresh` to populate the skill list.
								</p>
							)}
							<label className="block space-y-1">
								<span className="text-xs font-medium text-muted-foreground">
									Base branch (empty = bindings.yml default)
								</span>
								<input
									data-testid="automation-form-pin-base"
									value={baseBranch}
									onChange={(e) => setBaseBranch(e.target.value)}
									className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
								/>
							</label>
							{mode === "spawn" && (
								<label className="flex items-center gap-2 text-xs text-muted-foreground">
									<input
										type="checkbox"
										data-testid="automation-form-pin-worktree"
										checked={worktreeActive}
										onChange={(e) => setWorktreeActive(e.target.checked)}
										className="h-3.5 w-3.5"
									/>
									Spawn each issue in a fresh worktree
								</label>
							)}
							{mode === "loop" && (
								<p className="text-xs text-muted-foreground">
									Loop automations always use a persistent worktree.
								</p>
							)}
						</div>

						<div className="flex justify-end gap-2 pt-1">
							<button
								type="button"
								onClick={resetForm}
								className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
							>
								Cancel
							</button>
							<button
								type="submit"
								data-testid="automation-form-submit"
								disabled={createMut.isPending || updateMut.isPending}
								className="rounded-md border bg-foreground px-3 py-1.5 text-sm font-medium text-background transition disabled:opacity-40"
							>
								{editing ? "Update" : "Create"}
							</button>
						</div>
					</form>
				</div>
			)}

			{/* List */}
			<div className="min-h-0 flex-1">
				{isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
				{automations && automations.length === 0 && (
					<p className="text-sm text-muted-foreground">
						No automations yet. Create one to get started.
					</p>
				)}
				{automations && automations.length > 0 && (
					<div className="space-y-2">
						{automations.map((a) => (
							<div
								key={a.id}
								data-testid="automation-row"
								className="flex items-center gap-4 rounded-md border p-3"
							>
								{/* Toggle */}
								<label className="flex items-center gap-1.5 text-xs">
									<input
										data-testid="automation-enabled"
										type="checkbox"
										checked={a.enabled}
										onChange={(e) =>
											toggleMut.mutate({
												id: a.id,
												enabled: e.target.checked,
											})
										}
										className="h-3.5 w-3.5"
									/>
									{a.enabled ? "On" : "Off"}
								</label>

								<div className="min-w-0 flex-1">
									<p className="truncate text-sm font-medium">
										{a.template_title}
										{(a.preferred_skill ||
											a.preferred_agent ||
											a.preferred_model ||
											a.reasoning_effort ||
											a.base_branch ||
											a.worktree_active) && (
											<span
												data-testid="automation-pins-badge"
												className="ml-2 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground"
											>
												pinned
											</span>
										)}
									</p>
									<p className="truncate text-xs text-muted-foreground">
										{a.template_body}
									</p>
								</div>

								<span
									data-testid="automation-mode"
									className="text-xs font-medium uppercase text-muted-foreground"
								>
									{a.mode}
								</span>

								<span
									data-testid="automation-next-fire"
									className="text-xs text-muted-foreground whitespace-nowrap"
								>
									{nextLabel(a)}
								</span>

								<span
									data-testid="automation-remaining"
									className="text-xs text-muted-foreground whitespace-nowrap"
								>
									{countLabel(a)}
								</span>

								<button
									type="button"
									data-testid="automation-edit-btn"
									onClick={() => openEdit(a)}
									className="rounded px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
								>
									Edit
								</button>

								<button
									type="button"
									data-testid="automation-delete-btn"
									onClick={() => {
										if (
											!window.confirm(
												`Delete "${a.template_title}"? This cannot be undone.`,
											)
										)
											return;
										deleteMut.mutate(a.id);
									}}
									className="rounded px-2 py-1 text-xs text-red-500 hover:text-red-600"
								>
									Delete
								</button>
							</div>
						))}
					</div>
				)}
			</div>
		</div>
	);
}
