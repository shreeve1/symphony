"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { syncFromGithub } from "@/lib/api";

// ADR-0042 section 1: re-runnable "Sync from GitHub" button on the binding
// issue view. Present only when the binding's remote resolves to a GitHub repo
// (runtime resolvability is the opt-in, no bindings.yml field). Pressing it
// runs the insert-only reconcile and reports the inserted count. A re-press
// picks up newly-added child issues and never duplicates or mutates an
// existing row.
export function SyncFromGithubButton({
	binding,
	githubRepo,
}: {
	binding: string;
	githubRepo: string;
}) {
	const queryClient = useQueryClient();
	const [message, setMessage] = useState<string | null>(null);

	const mutation = useMutation({
		mutationFn: () => syncFromGithub(binding),
		onSuccess: (result) => {
			setMessage(
				`Synced ${githubRepo}: +${result.inserted} inserted, ${result.skipped} skipped`,
			);
			queryClient.invalidateQueries({ queryKey: ["issues", binding] });
			queryClient.invalidateQueries({ queryKey: ["bindings"] });
		},
		onError: (err: Error) => {
			setMessage(`Sync failed: ${err.message}`);
		},
	});

	const running = mutation.isPending;
	return (
		<div className="flex flex-col items-end gap-1">
			<button
				type="button"
				data-testid="sync-from-github-button"
				disabled={running}
				onClick={() => {
					setMessage(null);
					mutation.mutate();
				}}
				className="rounded-md border px-3 py-1.5 text-sm font-medium transition hover:border-foreground/30 hover:shadow disabled:opacity-50"
			>
				{running ? "Syncing…" : "Sync from GitHub"}
			</button>
			{message && (
				<span className="text-xs text-muted-foreground">{message}</span>
			)}
		</div>
	);
}