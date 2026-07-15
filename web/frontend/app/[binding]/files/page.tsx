"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { FileBrowser } from "@/components/FileBrowser";
import { FileEditor } from "@/components/FileEditor";

// Persisted state key for the file-pane "expand over tree" toggle. Mirrors
// `podium-flyout-maximized` (IssueFlyout) so the two features don't share
// state — one key per surface.
const EXPANDED_KEY = "podium-files-expanded";

export default function BindingFilesPage() {
	const { binding } = useParams<{ binding: string }>();
	const [selectedPath, setSelectedPath] = useState<string | null>(null);
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

	return (
		<div className="relative flex h-full">
			{/* Tree pane — hidden but mounted when expanded, so its open-dir
			    state and scroll position survive a toggle round-trip. The
			    Maximize/Restore control lives in this pane's header strip so it
			    doesn't overlap the FileEditor's Save button at the top-right of
			    the editor. */}
			<div
				data-testid="files-tree"
				className={`flex w-[280px] shrink-0 flex-col overflow-hidden border-r ${
					isExpanded ? "hidden" : ""
				}`}
			>
				<div className="flex items-center justify-between gap-2 border-b px-3 py-2">
					<h2 className="truncate text-sm font-semibold tracking-tight">
						{binding}
					</h2>
					<button
						type="button"
						data-testid="files-expand-toggle"
						aria-pressed={isExpanded}
						onClick={toggleExpanded}
						className="shrink-0 rounded-md border bg-background px-2.5 py-1 text-xs hover:bg-accent"
					>
						Maximize
					</button>
				</div>
				<div className="flex-1 overflow-y-auto p-2">
					<FileBrowser
						binding={binding}
						selectedPath={selectedPath}
						onSelect={setSelectedPath}
					/>
				</div>
			</div>
			<div className="min-w-0 flex-1">
				<FileEditor binding={binding} path={selectedPath} />
			</div>
			{/* When expanded the tree pane (and its toggle) is gone — anchor a
			    floating Restore handle bottom-right of the editor so the user
			    can still bring the tree back. */}
			{isExpanded && (
				<button
					type="button"
					data-testid="files-restore-toggle"
					aria-pressed={true}
					onClick={toggleExpanded}
					className="absolute bottom-3 right-3 z-10 rounded-md border bg-background px-3 py-1.5 text-sm shadow-sm hover:bg-accent"
				>
					Restore
				</button>
			)}
		</div>
	);
}
