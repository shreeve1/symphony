"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchDir, type FileEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FileBrowserProps {
	binding: string;
	selectedPath: string | null;
	onSelect: (path: string) => void;
}

interface DirNodeProps {
	binding: string;
	dirPath: string;
	depth: number;
	selectedPath: string | null;
	onSelect: (path: string) => void;
}

function rowPadding(depth: number): React.CSSProperties {
	// Indent nested entries; base padding kept in className.
	return { paddingLeft: `${depth * 12 + 8}px` };
}

function FileRow({
	entry,
	depth,
	selected,
	onClick,
}: {
	entry: FileEntry;
	depth: number;
	selected: boolean;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			data-testid="file-row"
			onClick={onClick}
			style={rowPadding(depth)}
			className={cn(
				"flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-sm transition-colors hover:bg-accent",
				selected && "bg-accent font-medium",
			)}
		>
			<span aria-hidden className="w-3 shrink-0 text-muted-foreground" />
			<span className="truncate">{entry.name}</span>
		</button>
	);
}

function DirNode({
	binding,
	dirPath,
	depth,
	selectedPath,
	onSelect,
}: DirNodeProps) {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["files", binding, dirPath],
		queryFn: () => fetchDir(binding, dirPath),
	});
	const [expanded, setExpanded] = useState<Set<string>>(new Set());

	const toggle = (path: string) => {
		setExpanded((prev) => {
			const next = new Set(prev);
			if (next.has(path)) {
				next.delete(path);
			} else {
				next.add(path);
			}
			return next;
		});
	};

	if (isLoading) {
		return (
			<p
				style={rowPadding(depth)}
				className="py-1 text-xs text-muted-foreground"
			>
				Loading…
			</p>
		);
	}
	if (isError || !data) {
		return (
			<p style={rowPadding(depth)} className="py-1 text-xs text-red-500">
				Failed to load
			</p>
		);
	}

	return (
		<>
			{data.items.map((entry) =>
				entry.is_directory ? (
					<div key={entry.path}>
						<button
							type="button"
							data-testid="dir-row"
							onClick={() => toggle(entry.path)}
							style={rowPadding(depth)}
							className="flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-sm transition-colors hover:bg-accent"
						>
							<span
								aria-hidden
								className="w-3 shrink-0 text-muted-foreground"
							>
								{expanded.has(entry.path) ? "▾" : "▸"}
							</span>
							<span className="truncate">{entry.name}</span>
						</button>
						{expanded.has(entry.path) && (
							<DirNode
								binding={binding}
								dirPath={entry.path}
								depth={depth + 1}
								selectedPath={selectedPath}
								onSelect={onSelect}
							/>
						)}
					</div>
				) : (
					<FileRow
						key={entry.path}
						entry={entry}
						depth={depth}
						selected={selectedPath === entry.path}
						onClick={() => onSelect(entry.path)}
					/>
				),
			)}
		</>
	);
}

export function FileBrowser({
	binding,
	selectedPath,
	onSelect,
}: FileBrowserProps) {
	return (
		<div data-testid="file-browser" className="flex flex-col gap-0.5">
			<DirNode
				binding={binding}
				dirPath=""
				depth={0}
				selectedPath={selectedPath}
				onSelect={onSelect}
			/>
		</div>
	);
}
