"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	fetchAutomations,
	createAutomation,
	updateAutomation,
	deleteAutomation,
	fetchBindings,
	type Automation,
	type AutomationCreate,
	type AutomationPatch,
} from "@/lib/api";
import { formatAge } from "@/lib/issues";

function remainingLabel(a: Automation): string {
	if (a.mode === "spawn") {
		if (a.spawn_run_count == null) return "Unlimited";
		const left = a.spawn_run_count - a.occurrences_fired;
		return `${Math.max(0, left)}`;
	}
	if (a.loop_iteration_cap == null) return "Unlimited";
	const left = a.loop_iteration_cap - a.occurrences_fired;
	return `${Math.max(0, left)}`;
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
			payload.spawn_run_count = runCount.trim()
				? parseInt(runCount, 10)
				: null;
		} else {
			const cap = parseInt(iterCap, 10);
			if (!isNaN(cap) && cap > 0) payload.loop_iteration_cap = cap;
			payload.loop_completion_marker = marker.trim() || "DONE.md";
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
				{isLoading && (
					<p className="text-sm text-muted-foreground">Loading…</p>
				)}
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
									</p>
									<p className="truncate text-xs text-muted-foreground">
										{a.template_body}
									</p>
								</div>

								<span data-testid="automation-mode" className="text-xs font-medium uppercase text-muted-foreground">
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
									{remainingLabel(a)} left
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
