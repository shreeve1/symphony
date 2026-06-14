"use client";

import {
	createContext,
	useContext,
	useEffect,
	useState,
	type ReactNode,
} from "react";
import {
	QueryClient,
	QueryClientProvider,
	useQueryClient,
} from "@tanstack/react-query";

import type { Issue, IssueDetail, Run } from "@/lib/api";

const RETRY_DELAYS_MS = [1_000, 2_000, 5_000, 10_000];

type ConnectionState = "connected" | "disconnected";

const ConnectionContext = createContext<ConnectionState>("disconnected");

// Tail events carry appended JSONL lines from a running issue's session file.
export interface TailEvent {
	issue_id: number;
	lines: string[];
}

const TailContext = createContext<TailEvent[]>([]);
const TailAppendContext = createContext<(event: TailEvent) => void>(() => {});

export function useTailEvents(): TailEvent[] {
	return useContext(TailContext);
}

export function useAppendTailEvent(): (event: TailEvent) => void {
	return useContext(TailAppendContext);
}

interface LiveMessage {
	type: "issue.created" | "issue.updated" | "run.updated" | "run.tail";
	id?: number;
	binding_name?: string;
	row: IssueDetail | Run;
	issue_id?: number;
	lines?: string[];
}

function websocketUrl() {
	const configured = process.env.NEXT_PUBLIC_PODIUM_API_ORIGIN;
	if (configured) {
		const url = new URL(configured);
		url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
		url.pathname = "/api/ws";
		url.search = "";
		url.hash = "";
		return url.toString();
	}
	const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
	return `${protocol}//${window.location.host}/api/ws`;
}

function upsertIssue(old: Issue[] | undefined, row: Issue) {
	if (!old) return old;
	const exists = old.some((issue) => issue.id === row.id);
	if (!exists) {
		const withoutMatchingTemp = old.filter(
			(issue) =>
				!(
					issue.id < 0 &&
					issue.binding_name === row.binding_name &&
					issue.title === row.title
				),
		);
		return [row, ...withoutMatchingTemp];
	}
	return old.map((issue) =>
		issue.id === row.id ? { ...issue, ...row } : issue,
	);
}

function updateRun(old: Run[] | undefined, row: Run) {
	if (!old) return old;
	return old.map((run) => (run.id === row.id ? { ...run, ...row } : run));
}

function LiveUpdates({
	onState,
	onTail,
}: {
	onState: (state: ConnectionState) => void;
	onTail: (event: TailEvent) => void;
}) {
	const queryClient = useQueryClient();

	useEffect(() => {
		let closed = false;
		let retry = 0;
		let socket: WebSocket | null = null;
		let timer: ReturnType<typeof setTimeout> | null = null;

		const refetchVisible = () => {
			queryClient.invalidateQueries({ queryKey: ["bindings"] });
			queryClient.invalidateQueries({ queryKey: ["issues"] });
		};

		const connect = () => {
			if (timer) {
				clearTimeout(timer);
				timer = null;
			}
			socket = new WebSocket(websocketUrl());
			socket.onopen = () => {
				retry = 0;
				onState("connected");
				refetchVisible();
			};
			socket.onmessage = (event) => {
				const message = JSON.parse(event.data) as LiveMessage;
				if (message.type === "issue.created") {
					const row = message.row as IssueDetail;
					queryClient.setQueryData<Issue[]>(
						["issues", message.binding_name ?? row.binding_name],
						(old) => upsertIssue(old, row),
					);
					queryClient.setQueryData(["issue", row.id], row);
					queryClient.invalidateQueries({ queryKey: ["inbox"] });
				}
				if (message.type === "issue.updated") {
					const row = message.row as IssueDetail;
					queryClient.setQueryData(["issue", row.id], row);
					queryClient.setQueriesData<Issue[]>({ queryKey: ["issues"] }, (old) =>
						upsertIssue(old, row),
					);
					queryClient.invalidateQueries({ queryKey: ["inbox"] });
				}
				if (message.type === "run.updated") {
					const row = message.row as Run;
					queryClient.setQueryData(["run", row.id], row);
					queryClient.setQueriesData<Run[]>({ queryKey: ["runs"] }, (old) =>
						updateRun(old, row),
					);
				}
				if (message.type === "run.tail") {
					onTail({
						issue_id: message.issue_id!,
						lines: message.lines ?? [],
					});
				}
			};
			socket.onclose = () => {
				if (closed) return;
				onState("disconnected");
				const delay =
					RETRY_DELAYS_MS[Math.min(retry, RETRY_DELAYS_MS.length - 1)];
				retry += 1;
				timer = setTimeout(connect, delay);
			};
			socket.onerror = () => socket?.close();
		};

		const handleOffline = () => onState("disconnected");
		const handleOnline = () => {
			if (socket?.readyState === WebSocket.OPEN) {
				onState("connected");
				refetchVisible();
				return;
			}
			socket?.close();
			connect();
		};

		window.addEventListener("offline", handleOffline);
		window.addEventListener("online", handleOnline);
		connect();
		return () => {
			closed = true;
			window.removeEventListener("offline", handleOffline);
			window.removeEventListener("online", handleOnline);
			if (timer) clearTimeout(timer);
			socket?.close();
		};
	}, [onState, queryClient]);

	return null;
}

export function ConnectionPill() {
	const state = useContext(ConnectionContext);
	if (state === "connected") return null;
	return (
		<span
			data-testid="connection-pill"
			className="rounded-full border border-amber-300/50 bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800"
		>
			Disconnected — retrying
		</span>
	);
}

const TAIL_BUFFER_PER_ISSUE = 1000;

export function QueryProvider({ children }: { children: ReactNode }) {
	const [connection, setConnection] = useState<ConnectionState>("disconnected");
	const [tailEvents, setTailEvents] = useState<TailEvent[]>([]);
	// One client per browser session. 5s staleTime per #012b: fetches are shared
	// and considered fresh for 5s so navigating between bindings does not refetch.
	const [client] = useState(
		() =>
			new QueryClient({
				defaultOptions: {
					queries: {
						staleTime: 5_000,
						refetchOnWindowFocus: false,
					},
				},
			}),
	);

	// Append incoming tail events, capped per issue to avoid unbounded growth.
	const handleTail = (event: TailEvent) => {
		setTailEvents((prev) => [...prev, event].slice(-TAIL_BUFFER_PER_ISSUE * 2)); // loose global cap
	};

	return (
		<QueryClientProvider client={client}>
			<ConnectionContext.Provider value={connection}>
				<TailAppendContext.Provider value={handleTail}>
					<TailContext.Provider value={tailEvents}>
						<LiveUpdates onState={setConnection} onTail={handleTail} />
						{children}
					</TailContext.Provider>
				</TailAppendContext.Provider>
			</ConnectionContext.Provider>
		</QueryClientProvider>
	);
}
