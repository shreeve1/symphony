import ReactMarkdown from "react-markdown";

// Read-only markdown renderer for issue descriptions and the Comments/Context
// bodies. Minimal Tailwind typography — no rich-text editing in Phase 1.
export function Markdown({ source }: { source: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:text-[0.85em] [&_h1]:text-base [&_h1]:font-semibold [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_strong]:font-semibold">
      <ReactMarkdown>{source}</ReactMarkdown>
    </div>
  );
}
