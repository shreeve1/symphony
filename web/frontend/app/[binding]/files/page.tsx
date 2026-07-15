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
			    state and scroll position survive a toggle round-trip. No Maximize
			    button in this header: the toggle is anchored bottom-right of the
			    page so it stays in the same spot in both states. */}
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
					/>
				</div>
			</div>
			<div className="min-w-0 flex-1">
				<FileEditor binding={binding} path={selectedPath} />
			</div>
			{/* Single control, anchored bottom-right of the page in both states.
			    Stays clear of the FileEditor's top-right Save button, doesn't
			    shift position when toggled, and the label flips Maximize ↔ Restore. */}
			<button
				type="button"
				data-testid="files-expand-toggle"
				aria-pressed={isExpanded}
				onClick={toggleExpanded}
				className="absolute bottom-3 right-3 z-10 rounded-md border bg-background px-3 py-1.5 text-sm shadow-sm hover:bg-accent"
			>
				{isExpanded ? "Restore" : "Maximize"}
			</button>
		</div>
	);
}
