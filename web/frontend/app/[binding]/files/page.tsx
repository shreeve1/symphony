"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { FileBrowser } from "@/components/FileBrowser";
import { FileEditor } from "@/components/FileEditor";
import { createFile, deleteFile } from "@/lib/api";

// Persisted state key for the file-pane "expand over tree" toggle. Mirrors
// `podium-flyout-maximized` (IssueFlyout) so the two features don't share
// state — one key per surface.
const EXPANDED_KEY = "podium-files-expanded";

export default function BindingFilesPage() {
	const { binding } = useParams<{ binding: string }>();
	const queryClient = useQueryClient();
	const [selectedPath, setSelectedPath] = useState<string | null>(null);
	// Folder that "New" creates into. "" = repo root; set by clicking a folder.
	const [targetDir, setTargetDir] = useState("");
	const [isExpanded, setIsExpanded] = useState(false);

	// SSR-safe hydration from localStorage. Mirrors the IssueFlyout pattern:
	// initialize false, sync after mount. Brief "Maximize" → "Restore" flash
	// if persisted=true is the same trade-off the flyout accepts.
	useEffect(() => {
		try {
			setIsExpanded(window.localStorage.getItem(EXPANDED_KEY) === "true");
		} catch {
			// Storage unavailable — keep in-memory false.
		}
	}, []);

	const toggleExpanded = useCallback(() => {
		setIsExpanded((value) => {
			const next = !value;
			try {
				window.localStorage.setItem(EXPANDED_KEY, String(next));
			} catch {
				// Storage unavailable — in-memory state still works for this session.
			}
			return next;
		});
	}, []);

	const createMutation = useMutation({
		mutationFn: (path: string) => createFile(binding, path),
		onSuccess: (_data, path) => {
			queryClient.invalidateQueries({ queryKey: ["files", binding] });
			setSelectedPath(path);
		},
	});

	const deleteMutation = useMutation({
		mutationFn: (path: string) => deleteFile(binding, path),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["files", binding] });
			setSelectedPath(null);
		},
	});

	const handleNew = useCallback(() => {
		const name = window.prompt(`New file name (in ${targetDir || "root"}):`);
		if (!name) return;
		createMutation.mutate(targetDir ? `${targetDir}/${name}` : name);
	}, [targetDir, createMutation]);

	const handleDelete = useCallback(() => {
		if (!selectedPath) return;
		if (!window.confirm(`Delete ${selectedPath}? This cannot be undone.`))
			return;
		deleteMutation.mutate(selectedPath);
	}, [selectedPath, deleteMutation]);

	return (
		<div className="relative flex h-full">
			{/* Tree pane — hidden but mounted when expanded, so its open-dir
			    state and scroll position survive a toggle round-trip. */}
			<div
				data-testid="files-tree"
				className={`flex w-[280px] shrink-0 flex-col overflow-hidden border-r ${
					isExpanded ? "hidden" : ""
				}`}
			>
				<h2 className="border-b px-3 py-2 text-sm font-semibold tracking-tight">
					{binding}
				</h2>
				<div className="flex-1 overflow-y-auto p-2">
					<FileBrowser
						binding={binding}
						selectedPath={selectedPath}
						onSelect={setSelectedPath}
						targetDir={targetDir}
						onTargetDir={setTargetDir}
					/>
				</div>
			</div>
			<div className="min-w-0 flex-1">
				<FileEditor
					binding={binding}
					path={selectedPath}
					isExpanded={isExpanded}
					onToggleExpanded={toggleExpanded}
					onNew={handleNew}
					onDelete={handleDelete}
				/>
			</div>
		</div>
	);
}
