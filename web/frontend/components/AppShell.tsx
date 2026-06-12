"use client";

import { usePathname, useRouter } from "next/navigation";
import { PanelLeft } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { ConnectionPill, QueryProvider } from "@/components/QueryProvider";
import { Sidebar } from "@/components/Sidebar";
import { logout } from "@/lib/api";

const SIDEBAR_KEY = "podium:sidebar-open";

export function AppShell({ children }: { children: ReactNode }) {
	const pathname = usePathname();
	const router = useRouter();
	const [checked, setChecked] = useState(false);
	const [sidebarOpen, setSidebarOpen] = useState(true);
	const isLogin = pathname === "/login";

	// Restore the collapse preference once on mount (SSR renders open).
	useEffect(() => {
		if (localStorage.getItem(SIDEBAR_KEY) === "0") setSidebarOpen(false);
	}, []);

	const toggleSidebar = () =>
		setSidebarOpen((open) => {
			const next = !open;
			localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
			return next;
		});

	useEffect(() => {
		if (isLogin) {
			setChecked(true);
			return;
		}
		let cancelled = false;
		setChecked(false);
		fetch("/api/auth/whoami")
			.then((response) => {
				if (!response.ok) throw new Error("unauthenticated");
			})
			.then(() => {
				if (!cancelled) setChecked(true);
			})
			.catch(() => {
				if (!cancelled) router.replace("/login");
			});
		return () => {
			cancelled = true;
		};
	}, [isLogin, router]);

	if (isLogin) return <>{children}</>;
	if (!checked) {
		return (
			<div className="flex h-screen w-screen items-center justify-center text-sm text-muted-foreground">
				Checking session…
			</div>
		);
	}

	return (
		<QueryProvider>
			<div className="flex h-screen w-screen overflow-hidden">
				{sidebarOpen && <Sidebar />}
				<div className="flex flex-1 flex-col overflow-hidden">
					<header className="flex h-14 shrink-0 items-center justify-between border-b px-6">
						<div className="flex items-center gap-3">
							<button
								type="button"
								aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
								aria-pressed={sidebarOpen}
								data-testid="sidebar-toggle"
								onClick={toggleSidebar}
								className="-ml-2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
							>
								<PanelLeft className="size-4" />
							</button>
							<h1 className="text-base font-semibold">Podium</h1>
						</div>
						<div className="flex items-center gap-3">
							<ConnectionPill />
							<button
								type="button"
								className="rounded-md border px-3 py-1 text-sm"
								onClick={async () => {
									await logout();
									router.replace("/login");
								}}
							>
								Logout
							</button>
						</div>
					</header>
					<main className="flex-1 overflow-auto p-6">{children}</main>
				</div>
			</div>
		</QueryProvider>
	);
}
