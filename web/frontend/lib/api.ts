// Thin client over the Podium FastAPI backend (#012a). Every call is a relative
// path so it flows through the Next rewrite proxy in next.config.mjs.

export interface Binding {
	name: string;
	display_name: string;
	color: string;
	sort_order: number;
	archived: boolean;
	binding_type: "infra" | "coding";
	pi_mode: "one-shot" | "rpc";
	claude_persist?: boolean;
	approval_enabled: boolean;
	is_remote: boolean;
	repo_name: string | null;
	host: string;
	// ADR-0042 section 1: runtime resolvability of the binding remote to a
	// GitHub repo. Non-null enables the Sync from GitHub button; null hides it.
	github_repo: string | null;
}

export interface Issue {
	id: number;
	binding_name: string;
	binding_type: string;
	title: string;
	description: string | null;
	state: string;
	priority: string | null;
	preferred_agent: string | null;
	preferred_model: string | null;
	preferred_skill: string | null;
	reasoning_effort: string | null;
	worktree_active: boolean;
	approval_required: boolean;
	approved: boolean;
	scheduled_for: string | null;
	worktree_path: string;
	worktree_branch: string;
	base_branch: string | null;
	created_at: string | null;
	updated_at: string | null;
	latest_run_id: number | null;
	latest_verdict: string | null;
	latest_run_state: string | null;
	last_event_at: string | null;
	blocked_by: number[];
	locks: string[];
	dependencies_satisfied: boolean;
	unsatisfied_blocked_by: number[];
	lock_conflicts: string[];
	hold: boolean;
	// Issue #461: distinguish operator / patrol / automation origin so the
	// UI can surface automation-spawned issues (issue #459 follow-up). Set
	// in the API row from issue.origin; absent rows fall back to 'operator'.
	origin: "operator" | "patrol" | "automation";
}

// Full issue record, including the markdown bodies the list endpoint omits.
export interface IssueDetail extends Issue {
	comments_md: string;
	context_md: string;
}

// Run history/detail row. cost_usd exists on the backend but is intentionally
// not rendered (cost visualization dropped per the UI grilling decision).
export interface Run {
	id: number;
	issue_id: number;
	agent: string | null;
	provider: string | null;
	model: string | null;
	state: string;
	verdict: string | null;
	summary: string | null;
	exit_code: number | null;
	cost_usd: number | null;
	input_tokens: number | null;
	output_tokens: number | null;
	worktree_path: string | null;
	branch_name: string | null;
	base_branch: string | null;
	log_path: string | null;
	skill_invoked: string | null;
	started_at: string | null;
	ended_at: string | null;
}

export type RunDetail = Run;

// Inbox item — a cross-binding issue awaiting operator attention.
export interface InboxItem {
	id: number;
	binding_name: string;
	binding_type: string;
	title: string;
	description: string | null;
	state: string;
	priority: string | null;
	preferred_agent: string | null;
	preferred_model: string | null;
	preferred_skill: string | null;
	reasoning_effort: string | null;
	worktree_active: boolean;
	approval_required: boolean;
	approved: boolean;
	scheduled_for: string | null;
	worktree_path: string;
	worktree_branch: string;
	base_branch: string | null;
	created_at: string | null;
	updated_at: string | null;
	latest_run_id: number | null;
	latest_verdict: string | null;
	latest_run_state: string | null;
	last_event_at: string | null;
	inbox_dismissed_at: string | null;
	blocked_by: number[];
	locks: string[];
	dependencies_satisfied: boolean;
	unsatisfied_blocked_by: number[];
	lock_conflicts: string[];
	hold: boolean;
}

// CLI-refreshed skill catalog row (#015).
export interface Skill {
	name: string;
	description: string | null;
	source: string | null;
}

// Operator-editable fields (#013). Subset semantics: send only changed keys.
export interface IssuePatch {
	title?: string;
	description?: string | null;
	state?: string;
	priority?: string | null;
	preferred_agent?: string | null;
	preferred_model?: string | null;
	preferred_skill?: string | null;
	reasoning_effort?: string;
	worktree_active?: boolean;
	approval_required?: boolean;
	approved?: boolean;
	hold?: boolean;
	scheduled_for?: string | null;
	base_branch?: string | null;
	comments_md?: string;
	context_md?: string;
	blocked_by?: number[];
	locks?: string[];
}

export interface ScheduleRequest {
	not_before: string;
	reason?: string;
}

// New-issue payload (#014). state is server-set ('todo'); sending it gets a
// 400. Omitted reasoning_effort/worktree_active/base_branch fall back to
// server defaults (high / false / bindings.yml).
export interface IssueCreate {
	description: string;
	priority?: string;
	preferred_skill?: string;
	preferred_agent?: string;
	preferred_model?: string;
	reasoning_effort?: string;
	worktree_active?: boolean;
	approval_required?: boolean;
	approved?: boolean;
	hold?: boolean;
	schedule?: ScheduleRequest;
	base_branch?: string;
	blocked_by?: number[];
	locks?: string[];
}

// Dropdown choices for the new-issue form. models come from models.yml with
// an owning agent tag; branches are the live local branches of the binding's
// repo (empty when unavailable).
export interface ModelOption {
	id: string;
	agent: string;
	label?: string;
	provider?: string;
	default?: boolean;
	// Reasoning efforts this model accepts (model-specific vocabulary). Absent
	// when the catalog entry declares none — the form then offers the full set.
	efforts?: string[];
}

export interface IssueOptions {
	agents: string[];
	models: ModelOption[];
	branches: string[];
}

// ── Attachments (#325) ──────────────────────────────────────────

export interface IssueAttachment {
	id: number;
	issue_id: number;
	display_name: string;
	content_type: string;
	size_bytes: number;
	created_at: string;
}

export const fetchAttachments = (issueId: number) =>
	getJSON<IssueAttachment[]>(`/api/issues/${issueId}/attachments`);

export function attachmentDownloadUrl(issueId: number, attachmentId: number) {
	return `/api/issues/${issueId}/attachments/${attachmentId}`;
}

export async function uploadAttachment(
	issueId: number,
	file: File,
): Promise<IssueAttachment> {
	const path = `/api/issues/${issueId}/attachments`;
	const form = new FormData();
	form.append("file", file);
	const res = await fetch(path, { method: "POST", body: form });
	if (!res.ok) {
		throw new Error(`POST ${path} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<IssueAttachment>;
}

export async function deleteAttachment(
	issueId: number,
	attachmentId: number,
): Promise<void> {
	const path = `/api/issues/${issueId}/attachments/${attachmentId}`;
	const res = await fetch(path, { method: "DELETE" });
	if (!res.ok) {
		throw new Error(`DELETE ${path} -> ${res.status} ${res.statusText}`);
	}
}

// ── Automations (ADR-0038) ────────────────────────────────────────

export interface Automation {
	id: number;
	binding_name: string;
	mode: "spawn" | "loop";
	enabled: boolean;
	template_title: string;
	template_body: string;
	spawn_interval_seconds: number | null;
	spawn_run_count: number | null;
	occurrences_fired: number;
	next_fire_at: string | null;
	loop_iteration_cap: number | null;
	loop_completion_marker: string;
	// Per-Issue dispatch pins (issue #459). Each nullable; the fire path
	// (tracker_podium.fire_due_spawn_automations /
	// reconcile_loop_automations) threads them into insert_issue_row.
	// base_branch falls back to the binding default at fire-time when NULL.
	preferred_skill: string | null;
	preferred_agent: string | null;
	preferred_model: string | null;
	reasoning_effort: string | null;
	base_branch: string | null;
	worktree_active: boolean;
	created_at: string;
	updated_at: string;
}

export interface AutomationCreate {
	mode: "spawn" | "loop";
	template_title: string;
	template_body: string;
	spawn_interval_seconds?: number;
	spawn_run_count?: number | null;
	// Issue #462: one-shot delay before the first spawn fire (create only).
	// Omitted = start immediately (next_fire_at NULL, fires next tick).
	start_delay_seconds?: number;
	loop_iteration_cap?: number;
	loop_completion_marker?: string;
	preferred_skill?: string | null;
	preferred_agent?: string | null;
	preferred_model?: string | null;
	reasoning_effort?: string | null;
	base_branch?: string | null;
	worktree_active?: boolean;
}

export interface AutomationPatch {
	enabled?: boolean;
	template_title?: string;
	template_body?: string;
	spawn_interval_seconds?: number | null;
	spawn_run_count?: number | null;
	// Issue #462: reschedule the next spawn fire on edit. start_immediately
	// resets next_fire_at to NULL; start_delay_seconds sets now + delay.
	start_immediately?: boolean;
	start_delay_seconds?: number;
	loop_iteration_cap?: number | null;
	loop_completion_marker?: string;
	preferred_skill?: string | null;
	preferred_agent?: string | null;
	preferred_model?: string | null;
	reasoning_effort?: string | null;
	base_branch?: string | null;
	worktree_active?: boolean;
}

export const fetchAutomations = (binding: string) =>
	getJSON<Automation[]>(
		`/api/bindings/${encodeURIComponent(binding)}/automations`,
	);

export async function createAutomation(
	binding: string,
	body: AutomationCreate,
): Promise<Automation> {
	const path = `/api/bindings/${encodeURIComponent(binding)}/automations`;
	const res = await fetch(path, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
	if (!res.ok) {
		throw new Error(`POST ${path} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<Automation>;
}

export async function updateAutomation(
	binding: string,
	id: number,
	patch: AutomationPatch,
): Promise<Automation> {
	const path = `/api/bindings/${encodeURIComponent(binding)}/automations/${id}`;
	const res = await fetch(path, {
		method: "PATCH",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(patch),
	});
	if (!res.ok) {
		throw new Error(`PATCH ${path} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<Automation>;
}

export async function deleteAutomation(
	binding: string,
	id: number,
): Promise<void> {
	const path = `/api/bindings/${encodeURIComponent(binding)}/automations/${id}`;
	const res = await fetch(path, { method: "DELETE" });
	if (!res.ok) {
		throw new Error(`DELETE ${path} -> ${res.status} ${res.statusText}`);
	}
}

export interface FileEntry {
	name: string;
	path: string;
	absolute_path: string;
	is_directory: boolean;
}

export interface DirListing {
	items: FileEntry[];
	path: string;
}

export interface FileContent {
	path: string;
	content: string;
	size: number;
	modified: string;
	editable: boolean;
	language: string;
}

async function getJSON<T>(path: string): Promise<T> {
	const res = await fetch(path);
	if (!res.ok) {
		throw new Error(`${path} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<T>;
}

export const fetchBindings = () => getJSON<Binding[]>("/api/bindings");

export const fetchSkills = (binding?: string) =>
	getJSON<Skill[]>(
		binding
			? `/api/skills?binding=${encodeURIComponent(binding)}`
			: "/api/skills",
	);

export const fetchInbox = () => getJSON<InboxItem[]>("/api/inbox");

export async function dismissIssue(id: number): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/dismiss`, { method: "POST" });
	if (!res.ok) {
		throw new Error(
			`POST /api/issues/${id}/dismiss -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}

// ADR-0042 section 1: the binding-page Sync from GitHub button shells to the
// insert-only reconcile (web.cli.podium_issues.sync_from_github) and reports
// the inserted/skipped counts. The endpoint is idempotent: a re-press picks
// up newly-added child issues and never duplicates or mutates an existing row.
export interface SyncFromGithubResult {
	inserted: number;
	skipped: number;
	lines: string[];
}

export async function syncFromGithub(
	binding: string,
): Promise<SyncFromGithubResult> {
	const url = `/api/bindings/${encodeURIComponent(binding)}/sync-from-github`;
	const res = await fetch(url, { method: "POST" });
	if (!res.ok) {
		const detail = await res.text();
		throw new Error(
			`POST ${url} -> ${res.status} ${res.statusText}: ${detail}`,
		);
	}
	return res.json() as Promise<SyncFromGithubResult>;
}

export const fetchBindingIssues = (name: string) =>
	getJSON<Issue[]>(`/api/bindings/${encodeURIComponent(name)}/issues`);

export const fetchIssueOptions = (name: string) =>
	getJSON<IssueOptions>(`/api/bindings/${encodeURIComponent(name)}/options`);

export const fetchIssue = (id: number) =>
	getJSON<IssueDetail>(`/api/issues/${id}`);

export const fetchIssueRuns = (id: number) =>
	getJSON<Run[]>(`/api/issues/${id}/runs`);

export const fetchRun = (id: number) => getJSON<RunDetail>(`/api/runs/${id}`);

// ── B3 live-tail catch-up (#35) ────────────────────────────────────
//
// Snapshot the active run's session JSONL via the REST endpoint. Used as the
// catch-up step on flyout-open and on WS reconnect so a freshly mounted panel
// can render the full tail before any live `run.tail` deltas arrive. The
// `line_cursors` array lets the client dedupe against the WS stream:
// any WS line whose `line_cursors[i] <= snapshot.cursor` is stale and
// should be dropped.
//
// Server returns 404 for completed/unknown runs; the caller surfaces the
// empty placeholder instead of an error so a just-finished run does not
// break the flyout open animation.

export interface RunTailSnapshot {
	run_id: number;
	source_id: string;
	from_cursor: number;
	cursor: number;
	lines: string[];
	line_cursors: number[];
}

export async function fetchRunTail(id: number): Promise<RunTailSnapshot> {
	const res = await fetch(`/api/runs/${id}/tail`);
	if (!res.ok) {
		// 404 is the documented signal that the run is no longer active or has
		// never produced a transcript. Surface as an empty snapshot so the
		// catch-up flow silently no-ops rather than throwing into the panel.
		if (res.status === 404) {
			return {
				run_id: id,
				source_id: "",
				from_cursor: 0,
				cursor: 0,
				lines: [],
				line_cursors: [],
			};
		}
		throw new Error(
			`GET /api/runs/${id}/tail -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<RunTailSnapshot>;
}

// Server-driven threshold for the tool-pill auto-cluster UI affordance
// (issue #35 criterion: "threshold server-driven, not hardcoded"). The
// current server contract does not expose it as a separate endpoint, so the
// client reads it from a build-time `NEXT_PUBLIC_TAIL_CLUSTER_THRESHOLD` env
// override and falls back to 3 (the spec's default). A nullish or non-finite
// value is coerced to 3 so a typo never disables clustering.
export function tailClusterThreshold(): number {
	const raw = process.env.NEXT_PUBLIC_TAIL_CLUSTER_THRESHOLD;
	const parsed = raw == null ? Number.NaN : Number(raw);
	return Number.isFinite(parsed) && parsed >= 2 ? Math.floor(parsed) : 3;
}

export const fetchDir = (binding: string, path: string) =>
	getJSON<DirListing>(
		`/api/bindings/${encodeURIComponent(binding)}/files?path=${encodeURIComponent(path)}`,
	);

export const fetchFile = (binding: string, path: string) =>
	getJSON<FileContent>(
		`/api/bindings/${encodeURIComponent(binding)}/files/content?path=${encodeURIComponent(path)}`,
	);

export async function saveFile(
	binding: string,
	path: string,
	content: string,
): Promise<{ message: string; path: string; size: number }> {
	const url = `/api/bindings/${encodeURIComponent(binding)}/files/content`;
	const res = await fetch(url, {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ path, content }),
	});
	if (!res.ok) {
		throw new Error(`PUT ${url} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<{ message: string; path: string; size: number }>;
}

export async function createFile(
	binding: string,
	path: string,
): Promise<{ message: string; path: string }> {
	const url = `/api/bindings/${encodeURIComponent(binding)}/files`;
	const res = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ path }),
	});
	if (!res.ok) {
		throw new Error(`POST ${url} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<{ message: string; path: string }>;
}

export async function deleteFile(
	binding: string,
	path: string,
): Promise<{ message: string; path: string }> {
	const url = `/api/bindings/${encodeURIComponent(binding)}/files/content?path=${encodeURIComponent(path)}`;
	const res = await fetch(url, { method: "DELETE" });
	if (!res.ok) {
		throw new Error(`DELETE ${url} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<{ message: string; path: string }>;
}

export async function login(password: string): Promise<void> {
	const res = await fetch("/api/auth/login", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ password }),
	});
	if (!res.ok) {
		throw new Error(`POST /api/auth/login -> ${res.status} ${res.statusText}`);
	}
}

export async function logout(): Promise<void> {
	const res = await fetch("/api/auth/logout", { method: "POST" });
	if (!res.ok) {
		throw new Error(`POST /api/auth/logout -> ${res.status} ${res.statusText}`);
	}
}

export async function fetchRunLog(id: number): Promise<string | null> {
	const res = await fetch(`/api/runs/${id}/log`);
	if (res.status === 404) return null;
	if (!res.ok) {
		throw new Error(
			`GET /api/runs/${id}/log -> ${res.status} ${res.statusText}`,
		);
	}
	return res.text();
}

export async function createIssue(
	binding: string,
	body: IssueCreate,
): Promise<IssueDetail> {
	const path = `/api/bindings/${encodeURIComponent(binding)}/issues`;
	const res = await fetch(path, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
	if (!res.ok) {
		throw new Error(`POST ${path} -> ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<IssueDetail>;
}

export async function patchIssue(
	id: number,
	patch: IssuePatch,
): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}`, {
		method: "PATCH",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(patch),
	});
	if (!res.ok) {
		let detail: string | undefined;
		try {
			detail = ((await res.json()) as { detail?: string }).detail;
		} catch {
			// Body not JSON — detail stays undefined.
		}
		const err: Error & { detail?: string } = new Error(
			`PATCH /api/issues/${id} -> ${res.status} ${res.statusText}`,
		);
		err.detail = detail;
		throw err;
	}
	return res.json() as Promise<IssueDetail>;
}

export async function scheduleIssue(
	id: number,
	body: ScheduleRequest,
): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/schedule`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
	if (!res.ok) {
		throw new Error(
			`POST /api/issues/${id}/schedule -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}

export async function unscheduleIssue(id: number): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/schedule`, { method: "DELETE" });
	if (!res.ok) {
		throw new Error(
			`DELETE /api/issues/${id}/schedule -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}

export async function postReply(
	id: number,
	body: string,
): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/reply`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ body }),
	});
	if (!res.ok) {
		throw new Error(
			`POST /api/issues/${id}/reply -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}

// Append-only comment (ADR-0017): adds to the thread without reopening or
// re-dispatching. Use for held/scheduled issues where /reply would 409 (todo)
// or wrongly trigger a run before the maintenance window.
export async function postComment(
	id: number,
	body: string,
): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/comment`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ body }),
	});
	if (!res.ok) {
		throw new Error(
			`POST /api/issues/${id}/comment -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}

export async function postSteer(
	id: number,
	body: string,
): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/steer`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ action: "steer", body }),
	});
	if (!res.ok) {
		throw new Error(
			`POST /api/issues/${id}/steer -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}

export async function postAbort(id: number): Promise<IssueDetail> {
	const res = await fetch(`/api/issues/${id}/steer`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ action: "abort" }),
	});
	if (!res.ok) {
		throw new Error(
			`POST /api/issues/${id}/steer -> ${res.status} ${res.statusText}`,
		);
	}
	return res.json() as Promise<IssueDetail>;
}
