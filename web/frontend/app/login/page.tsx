"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { login } from "@/lib/api";

export default function LoginPage() {
	const router = useRouter();
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [submitting, setSubmitting] = useState(false);

	async function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setSubmitting(true);
		setError(null);
		try {
			await login(password);
			router.replace("/");
		} catch {
			setError("Invalid password");
		} finally {
			setSubmitting(false);
		}
	}

	return (
		<main className="flex h-screen w-screen items-center justify-center bg-background p-6">
			<form
				onSubmit={onSubmit}
				className="flex w-full max-w-sm flex-col gap-4 rounded-lg border bg-card p-6 shadow-sm"
			>
				<div>
					<h1 className="text-lg font-semibold">Podium login</h1>
					<p className="text-sm text-muted-foreground">
						Enter shared operator password.
					</p>
				</div>
				<label className="flex flex-col gap-1 text-sm font-medium">
					Password
					<input
						type="password"
						value={password}
						onChange={(event) => setPassword(event.target.value)}
						className="rounded-md border bg-background px-3 py-2"
						autoComplete="current-password"
						autoFocus
					/>
				</label>
				{error && <p className="text-sm text-red-600">{error}</p>}
				<button
					type="submit"
					disabled={submitting}
					className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
				>
					{submitting ? "Logging in…" : "Log in"}
				</button>
			</form>
		</main>
	);
}
