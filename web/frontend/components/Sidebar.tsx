"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { fetchBindings, fetchInbox, type InboxItem } from "@/lib/api";
import { cn } from "@/lib/utils";

function relativeAge(iso: string | null | undefined): string {
  if (!iso) return "";
  const ms = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return "now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function stateBadge(state: string): { label: string; className: string } {
  if (state === "in_review")
    return { label: "In Review", className: "bg-yellow-100 text-yellow-800" };
  return { label: "Blocked", className: "bg-red-100 text-red-800" };
}

function InboxCard({
  item,
  color,
  active,
}: {
  item: InboxItem;
  color: string;
  active: boolean;
}) {
  const badge = stateBadge(item.state);
  return (
    <Link
      href={`/${item.binding_name}?issue=${item.id}`}
      data-testid="inbox-card"
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent",
        active && "bg-sidebar-accent font-medium",
      )}
    >
      <span
        aria-hidden
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="flex-1 truncate">{item.title}</span>
      <span
        className={cn(
          "shrink-0 rounded px-1 py-0.5 text-[10px] font-medium leading-none",
          badge.className,
        )}
      >
        {badge.label}
      </span>
      <span className="shrink-0 text-[10px] text-sidebar-foreground/50">
        {relativeAge(item.last_event_at ?? item.updated_at)}
      </span>
    </Link>
  );
}

export function Sidebar() {
  const params = useParams<{ binding?: string }>();
  const active = params?.binding;

  const { data: bindings, isLoading: bindingsLoading, isError: bindingsError } =
    useQuery({
      queryKey: ["bindings"],
      queryFn: fetchBindings,
    });

  const { data: inbox } = useQuery({
    queryKey: ["inbox"],
    queryFn: fetchInbox,
    refetchInterval: 10_000,
  });

  const colorMap = new Map(
    bindings?.map((b) => [b.name, b.color]) ?? [],
  );

  return (
    <aside data-testid="sidebar" className="flex h-full w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <Link
        href="/"
        className="flex h-14 items-center px-4 text-lg font-semibold tracking-tight"
      >
        Podium
      </Link>

      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-2">
        <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wider text-sidebar-foreground/50">
          Bindings
        </p>

        {bindingsLoading && (
          <p className="px-2 py-1 text-sm text-sidebar-foreground/60">
            Loading…
          </p>
        )}
        {bindingsError && (
          <p className="px-2 py-1 text-sm text-red-400">Failed to load bindings</p>
        )}

        {bindings?.map((binding) => (
          <Link
            key={binding.name}
            href={`/${binding.name}`}
            data-testid="binding-row"
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent",
              active === binding.name && "bg-sidebar-accent font-medium",
            )}
          >
            <span
              aria-hidden
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: binding.color }}
            />
            <span className="truncate">{binding.display_name}</span>
          </Link>
        ))}

        {inbox && inbox.length > 0 && (
          <>
            <p className="mt-2 px-2 pb-1 text-xs font-medium uppercase tracking-wider text-sidebar-foreground/50">
              Inbox ({inbox.length})
            </p>
            {inbox.map((item) => (
              <InboxCard
                key={item.id}
                item={item}
                color={colorMap.get(item.binding_name) ?? "#888888"}
                active={false}
              />
            ))}
          </>
        )}
      </nav>
    </aside>
  );
}
