"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
	attachmentDownloadUrl,
	deleteAttachment,
	fetchAttachments,
	uploadAttachment,
	type IssueAttachment,
} from "@/lib/api";

function formatBytes(n: number): string {
	if (n < 1024) return `${n} B`;
	if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
	return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function isImage(mime: string): boolean {
	return mime.startsWith("image/");
}

interface UploadSlot {
	file: File;
	status: "pending" | "error";
}

export function AttachmentPanel({ issueId }: { issueId: number }) {
	const queryClient = useQueryClient();
	const fileInputRef = useRef<HTMLInputElement>(null);
	const [slots, setSlots] = useState<UploadSlot[]>([]);
	const [dragOver, setDragOver] = useState(false);

	const attachments = useQuery({
		queryKey: ["attachments", issueId],
		queryFn: () => fetchAttachments(issueId),
	});

	const upload = useMutation({
		mutationFn: (file: File) => uploadAttachment(issueId, file),
		onMutate: (file) => {
			setSlots((prev) => [...prev, { file, status: "pending" }]);
		},
		onSuccess: (_data, file) => {
			setSlots((prev) => prev.filter((s) => s.file !== file));
			queryClient.invalidateQueries({ queryKey: ["attachments", issueId] });
		},
		onError: (_error, file) => {
			setSlots((prev) =>
				prev.map((s) =>
					s.file === file ? { ...s, status: "error" as const } : s,
				),
			);
		},
	});

	const destroy = useMutation({
		mutationFn: (id: number) => deleteAttachment(issueId, id),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["attachments", issueId] });
		},
	});

	const doUpload = useCallback(
		(files: FileList | File[]) => {
			for (const f of files) upload.mutate(f);
			// Clear the file input so re-picking the same file triggers onChange.
			if (fileInputRef.current) fileInputRef.current.value = "";
		},
		[upload],
	);

	const onDrop = useCallback(
		(e: React.DragEvent) => {
			e.preventDefault();
			setDragOver(false);
			if (e.dataTransfer.files.length > 0) doUpload(e.dataTransfer.files);
		},
		[doUpload],
	);

	const onPaste = useCallback(
		(e: ClipboardEvent) => {
			const items = e.clipboardData?.files;
			if (items && items.length > 0) doUpload(items);
		},
		[doUpload],
	);

	// ponytail: global paste listener — sufficient for this panel; if multiple
	// panels co-exist, scope to a focus-based ref.
	useEffect(() => {
		document.addEventListener("paste", onPaste);
		return () => document.removeEventListener("paste", onPaste);
	}, [onPaste]);

	const dismissSlot = (file: File) => {
		setSlots((prev) => prev.filter((s) => s.file !== file));
	};

	const list = attachments.data ?? [];
	const rows: (IssueAttachment | UploadSlot & { key: string })[] = [
		...slots.map((s) => ({ ...s, key: `slot-${s.file.name}` })),
		...list,
	];

	return (
		<div className="space-y-3" data-testid="attachment-panel">
			{/* Upload zone */}
			<div
				data-testid="attachment-drop-zone"
				onDragOver={(e) => {
					e.preventDefault();
					setDragOver(true);
				}}
				onDragLeave={() => setDragOver(false)}
				onDrop={onDrop}
				className={`rounded-md border-2 border-dashed p-4 text-center text-xs text-muted-foreground transition-colors ${
					dragOver ? "border-foreground bg-muted/40" : "border-muted"
				}`}
			>
				<input
					ref={fileInputRef}
					type="file"
					data-testid="attachment-file-input"
					className="sr-only"
					onChange={(e) => {
						if (e.target.files && e.target.files.length > 0)
							doUpload(e.target.files);
					}}
				/>
				<p>Drop files here, paste images, or</p>
				<button
					type="button"
					data-testid="attachment-pick-button"
					onClick={() => fileInputRef.current?.click()}
					className="mt-1 rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted/40"
				>
					Choose files
				</button>
			</div>

			{/* Attachment rows */}
			{rows.length === 0 && slots.length === 0 ? (
				<p className="text-xs text-muted-foreground">No attachments yet.</p>
			) : (
				<ul className="space-y-2" data-testid="attachment-list">
					{rows.map((row) => {
						if ("key" in row) {
							// Upload slot
							return (
								<li
									key={row.key}
									data-testid="attachment-slot"
									className="flex items-center gap-2 rounded-md border p-2 text-xs"
								>
									<span className="flex-1 truncate font-medium">
										{row.file.name}
									</span>
									{row.status === "pending" ? (
										<span className="text-muted-foreground">Uploading…</span>
									) : (
										<>
											<span className="text-red-500">Upload failed</span>
											<button
												type="button"
												data-testid="attachment-slot-dismiss"
												onClick={() => dismissSlot(row.file)}
												className="rounded border px-1.5 py-0.5 hover:bg-muted/40"
											>
												Dismiss
											</button>
										</>
									)}
								</li>
							);
						}

						// Stored attachment
						const a = row as IssueAttachment;
						const img = isImage(a.content_type);
						return (
							<li
								key={a.id}
								data-testid={`attachment-row-${a.id}`}
								className="flex items-start gap-2 rounded-md border p-2 text-xs"
							>
								{/* ponytail: cheap image preview — download URL as src.
                    Large images may be slow; lazy loading helps. */}
								{img && (
									<img
										src={attachmentDownloadUrl(issueId, a.id)}
										alt={a.display_name}
										loading="lazy"
										className="h-10 w-10 shrink-0 rounded object-cover"
									/>
								)}
								<div className="min-w-0 flex-1">
									<p className="truncate font-medium" title={a.display_name}>
										{a.display_name}
									</p>
									<p className="text-muted-foreground">
										{formatBytes(a.size_bytes)} · {a.content_type}
									</p>
									<p className="text-muted-foreground">
										{new Date(a.created_at).toLocaleString()}
									</p>
								</div>
								<div className="flex shrink-0 gap-1">
									<a
										href={attachmentDownloadUrl(issueId, a.id)}
										data-testid={`attachment-download-${a.id}`}
										className="rounded border px-1.5 py-0.5 hover:bg-muted/40"
										download={a.display_name}
									>
										Download
									</a>
									<button
										type="button"
										data-testid={`attachment-delete-${a.id}`}
										disabled={destroy.isPending}
										onClick={() => destroy.mutate(a.id)}
										className="rounded border px-1.5 py-0.5 text-red-600 hover:bg-red-50 disabled:opacity-50"
									>
										Delete
									</button>
								</div>
							</li>
						);
					})}
				</ul>
			)}
		</div>
	);
}


