import type { Metadata } from "next";

import "./globals.css";
import { ConnectionPill, QueryProvider } from "@/components/QueryProvider";
import { Sidebar } from "@/components/Sidebar";

export const metadata: Metadata = {
	title: "Podium",
	description: "Symphony operator console",
};

export default function RootLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return (
		<html lang="en">
			<body className="antialiased">
				<QueryProvider>
					<div className="flex h-screen w-screen overflow-hidden">
						<Sidebar />
						<div className="flex flex-1 flex-col overflow-hidden">
							<header className="flex h-14 shrink-0 items-center justify-between border-b px-6">
								<h1 className="text-base font-semibold">Podium</h1>
								<ConnectionPill />
							</header>
							<main className="flex-1 overflow-auto p-6">{children}</main>
						</div>
					</div>
				</QueryProvider>
			</body>
		</html>
	);
}
