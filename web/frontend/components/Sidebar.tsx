"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { fetchBindings } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const params = useParams<{ binding?: string }>();
  const active = params?.binding;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["bindings"],
    queryFn: fetchBindings,
  });

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
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

        {isLoading && (
          <p className="px-2 py-1 text-sm text-sidebar-foreground/60">
            Loading…
          </p>
        )}
        {isError && (
          <p className="px-2 py-1 text-sm text-red-400">Failed to load bindings</p>
        )}

        {data?.map((binding) => (
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
      </nav>
    </aside>
  );
}
