import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Read-only markdown renderer for issue descriptions and the Comments/Context
// bodies. Minimal Tailwind typography — no rich-text editing in Phase 1.
// remark-gfm adds GitHub tables, strikethrough, task lists, and autolinks
// (none of which are in CommonMark, so react-markdown needs the plugin).
export function Markdown({ source }: { source: string }) {
	return (
		<div className="space-y-2 text-sm leading-relaxed break-words [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:text-[0.85em] [&_h1]:text-base [&_h1]:font-semibold [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_pre]:max-w-full [&_pre]:whitespace-pre-wrap [&_pre]:break-words [&_strong]:font-semibold [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_td]:border [&_th]:px-2 [&_td]:px-2 [&_th]:py-1 [&_td]:py-1 [&_th]:text-left [&_th]:font-semibold [&_thead]:bg-muted">
			<ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
		</div>
	);
}
