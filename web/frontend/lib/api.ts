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

export interface FileEntry {
	name: string;
	path: string;
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

export const fetchSkills = () => getJSON<Skill[]>("/api/skills");

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

export const fetchBindingIssues = (name: string) =>
	getJSON<Issue[]>(`/api/bindings/${encodeURIComponent(name)}/issues`);

export const fetchIssueOptions = (name: string) =>
	getJSON<IssueOptions>(`/api/bindings/${encodeURIComponent(name)}/options`);

export const fetchIssue = (id: number) =>
	getJSON<IssueDetail>(`/api/issues/${id}`);

export const fetchIssueRuns = (id: number) =>
	getJSON<Run[]>(`/api/issues/${id}/runs`);

export const fetchRun = (id: number) => getJSON<RunDetail>(`/api/runs/${id}`);

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
