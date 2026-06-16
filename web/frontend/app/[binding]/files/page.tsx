"use client";

import { useState } from "react";
import { useParams } from "next/navigation";

import { FileBrowser } from "@/components/FileBrowser";
import { FileEditor } from "@/components/FileEditor";

export default function BindingFilesPage() {
	const { binding } = useParams<{ binding: string }>();
	const [selectedPath, setSelectedPath] = useState<string | null>(null);

	return (
		<div className="flex h-full">
			<div className="w-[280px] shrink-0 overflow-y-auto border-r p-2">
				<h2 className="px-2 pb-2 text-sm font-semibold tracking-tight">
					{binding}
				</h2>
				<FileBrowser
					binding={binding}
					selectedPath={selectedPath}
					onSelect={setSelectedPath}
				/>
			</div>
			<div className="min-w-0 flex-1">
				<FileEditor binding={binding} path={selectedPath} />
			</div>
		</div>
	);
}
