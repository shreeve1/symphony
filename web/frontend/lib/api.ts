// Thin client over the Podium FastAPI backend (#012a). Every call is a relative
// path so it flows through the Next rewrite proxy in next.config.mjs.

export interface Binding {
  name: string;
  display_name: string;
  color: string;
  sort_order: number;
  archived: boolean;
}

export interface Issue {
  id: number;
  binding_name: string;
  title: string;
  description: string | null;
  state: string;
  priority: string | null;
  preferred_agent: string | null;
  preferred_model: string | null;
  preferred_skill: string | null;
  reasoning_effort: string | null;
  worktree_active: boolean;
  max_duration_seconds: number | null;
  base_branch: string | null;
  created_at: string | null;
  updated_at: string | null;
  latest_run_id: number | null;
  latest_verdict: string | null;
  latest_run_state: string | null;
  last_event_at: string | null;
}

// Full issue record, including the markdown bodies the list endpoint omits.
export interface IssueDetail extends Issue {
  comments_md: string;
  context_md: string;
}

// Run history row. cost_usd exists on the backend but is intentionally not
// surfaced in Phase 1 (cost visualization dropped per the UI grilling decision).
export interface Run {
  id: number;
  issue_id: number;
  verdict: string | null;
  model: string | null;
  state: string;
  started_at: string | null;
  ended_at: string | null;
}

// Placeholder skill catalog row (real catalog ships in #015).
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
  max_duration_seconds?: number | null;
  base_branch?: string | null;
  comments_md?: string;
  context_md?: string;
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

export const fetchBindingIssues = (name: string) =>
  getJSON<Issue[]>(`/api/bindings/${encodeURIComponent(name)}/issues`);

export const fetchIssue = (id: number) =>
  getJSON<IssueDetail>(`/api/issues/${id}`);

export const fetchIssueRuns = (id: number) =>
  getJSON<Run[]>(`/api/issues/${id}/runs`);

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
    throw new Error(`PATCH /api/issues/${id} -> ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<IssueDetail>;
}
