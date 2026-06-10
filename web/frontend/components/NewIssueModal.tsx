"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createIssue,
  fetchSkills,
  type Issue,
  type IssueCreate,
} from "@/lib/api";

const PRIORITIES = ["low", "med", "high", "urgent"] as const;

// Optimistic create (#014): prepend a temp card to the board cache on submit,
// swap it for the canonical server row on success, roll back on error, and
// refetch once the write settles. The canonical row is the full detail shape
// (a superset of Issue), so the list cache transiently holds one wider row
// until the settle-refetch trims it — harmless, extra fields are ignored.
function useCreateIssue(binding: string) {
  const queryClient = useQueryClient();
  const key = ["issues", binding];
  return useMutation({
    mutationFn: (body: IssueCreate) => createIssue(binding, body),
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<Issue[]>(key);
      const temp: Issue = {
        id: -Date.now(), // negative: cannot collide with a server-assigned id
        binding_name: binding,
        title: body.title,
        description: body.description ?? null,
        state: "todo",
        priority: body.priority ?? null,
        preferred_agent: null,
        preferred_model: null,
        preferred_skill: body.preferred_skill ?? null,
        reasoning_effort: "high",
        worktree_active: false,
        max_duration_seconds: null,
        base_branch: null,
        created_at: null,
        updated_at: null,
        latest_run_id: null,
        latest_verdict: null,
        latest_run_state: null,
        last_event_at: null,
      };
      queryClient.setQueryData<Issue[]>(key, (old) => [temp, ...(old ?? [])]);
      return { previous, tempId: temp.id };
    },
    onSuccess: (row, _body, context) => {
      queryClient.setQueryData<Issue[]>(key, (old) =>
        (old ?? []).map((issue) => (issue.id === context.tempId ? row : issue)),
      );
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

function NewIssueModal({
  binding,
  onClose,
}: {
  binding: string;
  onClose: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("");
  const [skill, setSkill] = useState("");
  const titleRef = useRef<HTMLInputElement | null>(null);

  const create = useCreateIssue(binding);
  // Same catalog feed as the flyout chip: free-text skill would 422 on the FK.
  const skills = useQuery({ queryKey: ["skills"], queryFn: fetchSkills });

  useEffect(() => titleRef.current?.focus(), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || create.isPending) return;
    // The optimistic card carries the board UI immediately, but the modal only
    // closes on success: on failure the temp card silently rolls back, so the
    // still-open modal (typed values intact + error line) is the only place
    // the operator learns the create didn't land.
    create.mutate(
      {
        title: trimmed,
        ...(description.trim() && { description: description.trim() }),
        ...(priority && { priority }),
        ...(skill && { preferred_skill: skill }),
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
              Title
            </span>
            <input
              ref={titleRef}
              data-testid="new-issue-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-xs font-medium text-muted-foreground">
              Description
            </span>
            <textarea
              data-testid="new-issue-description"
              value={description}
              rows={4}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-md border bg-transparent px-2 py-1.5 font-mono text-xs outline-none focus:border-foreground/40"
            />
          </label>

          <div className="flex gap-3">
            <label className="block flex-1 space-y-1">
              <span className="text-xs font-medium text-muted-foreground">
                Priority
              </span>
              <select
                data-testid="new-issue-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full cursor-pointer rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none"
              >
                <option value="">—</option>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>

            <label className="block flex-1 space-y-1">
              <span className="text-xs font-medium text-muted-foreground">
                Skill
              </span>
              <select
                data-testid="new-issue-skill"
                value={skill}
                onChange={(e) => setSkill(e.target.value)}
                className="w-full cursor-pointer rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none"
              >
                <option value="">—</option>
                {(skills.data ?? []).map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

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
              disabled={!title.trim() || create.isPending}
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
