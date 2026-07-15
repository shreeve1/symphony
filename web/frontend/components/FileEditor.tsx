"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { OnMount } from "@monaco-editor/react";

import { fetchFile, saveFile } from "@/lib/api";
import { setupMonaco } from "@/lib/monaco";

// Monaco touches `window`; load it client-only so it never runs during SSR.
const Editor = dynamic(
	() => import("@monaco-editor/react").then((mod) => mod.Editor),
	{
		ssr: false,
		loading: () => (
			<p className="p-4 text-sm text-muted-foreground">Loading editor…</p>
		),
	},
);

interface FileEditorProps {
	binding: string;
	path: string | null;
	isExpanded: boolean;
	onToggleExpanded: () => void;
	onNew: () => void;
	onDelete: () => void;
}

// getJSON throws `Error("<url> -> <status> <statusText>")`. Pull the numeric
// status back out so we can map it to a friendly message.
function statusFromError(error: unknown): number | null {
	if (!(error instanceof Error)) return null;
	const match = error.message.match(/-> (\d{3})\b/);
	return match ? Number(match[1]) : null;
}

function errorMessage(error: unknown): string {
	switch (statusFromError(error)) {
		case 404:
			return "File not found.";
		case 400:
			return "This file can’t be opened (binary or non-editable).";
		case 413:
			return "File is too large to open (over 10MB).";
		default:
			return error instanceof Error ? error.message : "Failed to load file.";
	}
}

export function FileEditor({
	binding,
	path,
	isExpanded,
	onToggleExpanded,
	onNew,
	onDelete,
}: FileEditorProps) {
	const queryClient = useQueryClient();
	const [buffer, setBuffer] = useState("");
	const saveRef = useRef<() => void>(() => {});

	useEffect(() => {
		setupMonaco();
	}, []);

	const { data, isLoading, isError, error } = useQuery({
		queryKey: ["file", binding, path],
		queryFn: () => fetchFile(binding, path as string),
		enabled: Boolean(path),
	});

	// Reset local buffer whenever a new file loads (or reloads).
	useEffect(() => {
		if (data) setBuffer(data.content);
	}, [data]);

	const readOnly = data?.editable === false;
	const dirty = Boolean(data) && buffer !== data?.content;

	const saveMutation = useMutation({
		mutationFn: () => saveFile(binding, path as string, buffer),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["file", binding, path] });
		},
	});

	const canSave = Boolean(path) && dirty && !readOnly && !saveMutation.isPending;

	// Keep a stable ref the Monaco keybinding can call without re-mounting.
	saveRef.current = () => {
		if (canSave) saveMutation.mutate();
	};

	useEffect(() => {
		const handler = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
				e.preventDefault();
				saveRef.current();
			}
		};
		window.addEventListener("keydown", handler);
		return () => window.removeEventListener("keydown", handler);
	}, []);

	const handleMount: OnMount = (editor, monaco) => {
		editor.addCommand(
			monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
			() => saveRef.current(),
		);
	};

	// Toolbar sits at the top-right of the editor pane in every state (empty
	// too), so New/Save/Delete/Maximize stay in one fixed spot.
	const toolbar = (
		<div className="flex shrink-0 items-center gap-2">
			<button
				type="button"
				data-testid="file-new"
				onClick={onNew}
				className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
			>
				New
			</button>
			<button
				type="button"
				data-testid="file-save"
				onClick={() => saveMutation.mutate()}
				disabled={!canSave}
				className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
			>
				{saveMutation.isPending ? "Saving…" : "Save"}
			</button>
			<button
				type="button"
				data-testid="file-delete"
				onClick={onDelete}
				disabled={!path}
				className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-accent"
			>
				Delete
			</button>
			<button
				type="button"
				data-testid="files-expand-toggle"
				aria-pressed={isExpanded}
				onClick={onToggleExpanded}
				className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
			>
				{isExpanded ? "Restore" : "Maximize"}
			</button>
		</div>
	);

	if (!path) {
		return (
			<div data-testid="file-editor" className="flex h-full flex-col">
				<div className="flex items-center justify-end gap-2 border-b px-4 py-2">
					{toolbar}
				</div>
				<div
					data-testid="file-editor-empty"
					className="flex flex-1 items-center justify-center text-sm text-muted-foreground"
				>
					Select a file
				</div>
			</div>
		);
	}

	return (
		<div data-testid="file-editor" className="flex h-full flex-col">
			<div className="flex items-center justify-between gap-2 border-b px-4 py-2">
				<div className="min-w-0">
					<p className="truncate text-sm font-medium">{path}</p>
					{readOnly && (
						<p
							data-testid="file-editor-readonly"
							className="text-xs text-amber-500"
						>
							read-only
						</p>
					)}
				</div>
				{toolbar}
			</div>

			{saveMutation.isError && (
				<p
					data-testid="file-save-error"
					className="border-b bg-red-500/10 px-4 py-2 text-sm text-red-500"
				>
					{errorMessage(saveMutation.error)}
				</p>
			)}

			<div className="min-h-0 flex-1">
				{isLoading && (
					<p className="p-4 text-sm text-muted-foreground">Loading…</p>
				)}
				{isError && (
					<p
						data-testid="file-load-error"
						className="p-4 text-sm text-red-500"
					>
						{errorMessage(error)}
					</p>
				)}
				{data && (
					<Editor
						height="100%"
						theme="vs-dark"
						language={data.language}
						value={buffer}
						onChange={(value) => setBuffer(value ?? "")}
						onMount={handleMount}
						options={{ readOnly, minimap: { enabled: false } }}
					/>
				)}
			</div>
		</div>
	);
}
