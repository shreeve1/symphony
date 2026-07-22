"use client";

import { useCallback, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { fetchBindingIssues, fetchBindings } from "@/lib/api";
import { issueListRefetchIntervalMs } from "@/lib/polling";
import { KanbanBoard } from "@/components/KanbanBoard";
import { NewIssueButton } from "@/components/NewIssueModal";
import { SyncFromGithubButton } from "@/components/SyncFromGithubButton";

export default function BindingPage() {
	const { binding } = useParams<{ binding: string }>();
	const searchParams = useSearchParams();
	const deepLinkIssueId = searchParams.get("issue")
		? Number(searchParams.get("issue"))
		: null;
	// F4: a freshly created issue opens the flyout automatically. The modal
	// calls back with the new id after finishIssue settles (so staged
	// attachments + the trailing release PATCH have landed); we mirror it
	// into initialIssueId via the same path the deep-link uses, and let the
	// KanbanBoard's existing useEffect sync it into the open flyout.
	const [createdIssueId, setCreatedIssueId] = useState<number | null>(null);
	const initialIssueId = createdIssueId ?? deepLinkIssueId;
	const handleCreated = useCallback((issueId: number) => {
		setCreatedIssueId(issueId);
	}, []);

	const { data, isLoading, isError } = useQuery({
		queryKey: ["issues", binding],
		queryFn: () => fetchBindingIssues(binding),
		enabled: Boolean(binding),
		refetchInterval: (query) => issueListRefetchIntervalMs(query.state.data),
		refetchOnWindowFocus: true,
	});

	// ADR-0042 section 1: runtime resolvability of the binding's git remote to
	// a GitHub repo is the opt-in signal. The Sync button only renders when
	// `github_repo` is non-null.
	const { data: bindings } = useQuery({
		queryKey: ["bindings"],
		queryFn: fetchBindings,
	});
	const currentBinding = bindings?.find((b) => b.name === binding);
	const githubRepo = currentBinding?.github_repo ?? null;

	return (
		<div className="flex h-full flex-col gap-4">
			<div className="flex items-center justify-between">
				<h2 className="text-2xl font-semibold tracking-tight">{binding}</h2>
				<div className="flex items-center gap-2">
					{githubRepo && (
						<SyncFromGithubButton binding={binding} githubRepo={githubRepo} />
					)}
					<NewIssueButton binding={binding} onCreated={handleCreated} />
				</div>
			</div>

			<div className="min-h-0 flex-1">
				{isLoading && (
					<p className="text-sm text-muted-foreground">Loading issues…</p>
				)}
				{isError && (
					<p className="text-sm text-red-500">Failed to load issues</p>
				)}
				{data && (
					<KanbanBoard
						issues={data}
						initialIssueId={initialIssueId}
						autoFocusReply={createdIssueId != null}
					/>
				)}
			</div>
		</div>
	);
}
