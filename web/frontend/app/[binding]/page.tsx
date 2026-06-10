"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { fetchBindingIssues } from "@/lib/api";
import { KanbanBoard } from "@/components/KanbanBoard";
import { NewIssueButton } from "@/components/NewIssueModal";

export default function BindingPage() {
  const { binding } = useParams<{ binding: string }>();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["issues", binding],
    queryFn: () => fetchBindingIssues(binding),
    enabled: Boolean(binding),
  });

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">{binding}</h2>
        <NewIssueButton binding={binding} />
      </div>

      <div className="min-h-0 flex-1">
        {isLoading && (
          <p className="text-sm text-muted-foreground">Loading issues…</p>
        )}
        {isError && <p className="text-sm text-red-500">Failed to load issues</p>}
        {data && <KanbanBoard issues={data} />}
      </div>
    </div>
  );
}
