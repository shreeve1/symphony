"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ConnectionPill, QueryProvider } from "@/components/QueryProvider";
import { Sidebar } from "@/components/Sidebar";
import { logout } from "@/lib/api";

export function AppShell({ children }: { children: ReactNode }) {
	const pathname = usePathname();
	const router = useRouter();
	const [checked, setChecked] = useState(false);
	const isLogin = pathname === "/login";

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
				<Sidebar />
				<div className="flex flex-1 flex-col overflow-hidden">
					<header className="flex h-14 shrink-0 items-center justify-between border-b px-6">
						<h1 className="text-base font-semibold">Podium</h1>
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
