import type {
  DraggableAttributes,
  DraggableSyntheticListeners,
} from "@dnd-kit/core";
import { Bot } from "lucide-react";

import type { Issue } from "@/lib/api";
import { formatAge } from "@/lib/issues";
import { cn } from "@/lib/utils";

// Per-agent pill colour. Falls back to a neutral muted style for unknown agents.
const AGENT_STYLE: Record<string, string> = {
  claude: "bg-orange-100 text-orange-700",
  pi: "bg-violet-100 text-violet-700",
};

// Human label for the agent slug.
const AGENT_LABEL: Record<string, string> = {
  claude: "Claude",
  pi: "Pi",
};

// Agent + model quick-view. Shows the issue's preferred agent (colour-coded)
// and model; renders "default" when neither is pinned on the issue.
function ScheduledTag({ scheduledFor }: { scheduledFor: string | null }) {
  if (!scheduledFor) return null;
  return (
    <span
      data-testid="scheduled-chip"
      title={`Scheduled: ${scheduledFor}`}
      className="rounded-md bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700"
    >
      Scheduled
    </span>
  );
}

function AgentTag({
  agent,
  model,
}: {
  agent: string | null;
  model: string | null;
}) {
  if (!agent && !model) {
    return (
      <span className="text-[11px] text-muted-foreground">default agent</span>
    );
  }
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span
        data-testid="agent-pill"
        className={cn(
          "inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
          (agent && AGENT_STYLE[agent]) ?? "bg-muted text-muted-foreground",
        )}
      >
        <Bot className="size-3" />
        {(agent && AGENT_LABEL[agent]) ?? agent ?? "agent"}
      </span>
      {model && (
        <span className="truncate text-[11px] text-muted-foreground" title={model}>
          {model}
        </span>
      )}
    </span>
  );
}

// A single board card: title, agent/model quick-view, age. The drag props are
// supplied by KanbanBoard's useDraggable wrapper; when omitted (e.g. the
// DragOverlay clone) the card renders as a plain clickable button.
export function IssueCard({
  issue,
  onClick,
  dragRef,
  dragListeners,
  dragAttributes,
  isDragging,
}: {
  issue: Issue;
  onClick?: () => void;
  dragRef?: (element: HTMLElement | null) => void;
  dragListeners?: DraggableSyntheticListeners;
  dragAttributes?: DraggableAttributes;
  isDragging?: boolean;
}) {
  return (
    <button
      ref={dragRef}
      type="button"
      data-testid="issue-card"
      onClick={onClick}
      className={cn(
        "w-full rounded-lg border bg-background p-3 text-left shadow-sm transition hover:border-foreground/30 hover:shadow",
        isDragging && "opacity-40",
      )}
      {...dragAttributes}
      {...dragListeners}
    >
      <p className="text-sm font-medium leading-snug">{issue.title}</p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <AgentTag agent={issue.preferred_agent} model={issue.preferred_model} />
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {formatAge(issue.last_event_at)}
        </span>
      </div>
      <ScheduledTag scheduledFor={issue.scheduled_for} />
    </button>
  );
}
