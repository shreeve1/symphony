"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	dismissIssue,
	fetchBindings,
	fetchInbox,
	type Binding,
	type InboxItem,
} from "@/lib/api";
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

function InboxCard({
	item,
	color,
	active,
	onDismiss,
}: {
	item: InboxItem;
	color: string;
	active: boolean;
	onDismiss: (id: number) => void;
}) {
	return (
		<div
			data-testid="inbox-card"
			className={cn(
				"group flex items-center rounded-md text-sm transition-colors hover:bg-sidebar-accent",
				active && "bg-sidebar-accent font-medium",
			)}
		>
			<Link
				href={`/${item.binding_name}?issue=${item.id}`}
				className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5"
			>
				<span
					aria-hidden
					className="size-2 shrink-0 rounded-full"
					style={{ backgroundColor: color }}
				/>
				<span className="flex-1 truncate">{item.title}</span>
				<span className="shrink-0 text-[10px] text-sidebar-foreground/50">
					{relativeAge(item.last_event_at ?? item.updated_at)}
				</span>
			</Link>
			<button
				type="button"
				aria-label={`Dismiss ${item.title} from inbox`}
				data-testid="inbox-dismiss"
				onClick={() => onDismiss(item.id)}
				className="mr-1 flex size-5 shrink-0 items-center justify-center rounded text-xs opacity-0 transition-opacity hover:bg-sidebar-accent group-hover:opacity-100 focus:opacity-100"
				title="Dismiss from Inbox"
			>
				✓
			</button>
		</div>
	);
}

export function Sidebar() {
	const params = useParams<{ binding?: string }>();
	const active = params?.binding;

	const {
		data: bindings,
		isLoading: bindingsLoading,
		isError: bindingsError,
	} = useQuery({
		queryKey: ["bindings"],
		queryFn: fetchBindings,
	});

	const { data: inbox } = useQuery({
		queryKey: ["inbox"],
		queryFn: fetchInbox,
		refetchInterval: 10_000,
	});

	const queryClient = useQueryClient();
	const dismissMutation = useMutation({
		mutationFn: dismissIssue,
		onMutate: async (id: number) => {
			await queryClient.cancelQueries({ queryKey: ["inbox"] });
			const previous = queryClient.getQueryData<InboxItem[]>(["inbox"]);
			queryClient.setQueryData<InboxItem[]>(["inbox"], (old) =>
				old?.filter((item) => item.id !== id),
			);
			return { previous };
		},
		onError: (_error, _id, context) => {
			if (context?.previous) {
				queryClient.setQueryData(["inbox"], context.previous);
			}
		},
		onSettled: () => {
			queryClient.invalidateQueries({ queryKey: ["inbox"] });
		},
	});

	const colorMap = new Map(bindings?.map((b) => [b.name, b.color]) ?? []);

	// Group bindings by host: local bindings share the server hostname,
	// remote bindings group under their own name. ponytail: host label is
	// derived — no config field. Ceiling: two repos on one remote host make
	// two groups; upgrade path = resolve remote.host via ~/.ssh/config alias.
	const bindingGroups: ReadonlyArray<readonly [string, Binding[]]> = (() => {
		if (!bindings) return [];
		const map = new Map<string, Binding[]>();
		for (const b of bindings) {
			const list = map.get(b.host);
			if (list) list.push(b);
			else map.set(b.host, [b]);
		}
		const localHost = bindings.find((b) => !b.is_remote)?.host;
		return [...map.entries()]
			.sort(([a], [b]) =>
				a === localHost ? -1 : b === localHost ? 1 : a.localeCompare(b),
			)
			.map(([host, list]) => [
				host,
				[...list].sort((a, b) =>
					(a.repo_name ?? a.display_name).localeCompare(
						b.repo_name ?? b.display_name,
					),
				),
			]);
	})();

	return (
		<aside
			data-testid="sidebar"
			className="relative z-50 flex h-full w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground"
		>
			<Link
				href="/"
				className="flex h-14 items-center px-4 text-lg font-semibold tracking-tight"
			>
				Podium
			</Link>

			<nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-2">
				{bindingsLoading && (
					<p className="px-2 py-1 text-sm text-sidebar-foreground/60">
						Loading…
					</p>
				)}
				{bindingsError && (
					<p className="px-2 py-1 text-sm text-red-400">
						Failed to load bindings
					</p>
				)}

				{bindingGroups.map(([host, list]) => (
					<div key={host} data-testid="binding-group">
						<p className="px-2 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/60">
							{host}
						</p>
						{list.map((binding) => {
							const label = binding.repo_name ?? binding.display_name;
							return (
								<div key={binding.name}>
									<Link
										href={`/${binding.name}`}
										data-testid="binding-row"
										className={cn(
											"flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent",
											active === binding.name &&
												"bg-sidebar-accent font-medium",
										)}
									>
										<span
											aria-hidden
											className="size-2 shrink-0 rounded-full"
											style={{ backgroundColor: binding.color }}
										/>
										<span className="truncate">{label}</span>
									</Link>
									{active === binding.name && (
										<Link
											href={`/${binding.name}/files`}
											data-testid="binding-files-link"
											className="ml-4 flex items-center rounded-md px-2 py-1 text-xs text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent"
										>
											Files
										</Link>
									)}
								</div>
							);
						})}
					</div>
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
								onDismiss={(id) => dismissMutation.mutate(id)}
							/>
						))}
					</>
				)}
			</nav>
		</aside>
	);
}
