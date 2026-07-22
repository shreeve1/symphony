"use client";

// Markdown + sanitizer + syntax-highlighter pipeline for chat bubbles.
//
// The chat flyout must render agent text (markdown) safely, so the order
// is: marked.parse() -> DOMPurify.sanitize() -> Prism.highlightAllUnder()
// (applied at mount, see <MarkdownBubble> in SessionTailPanel). Prism
// walks only the post-sanitize DOM so it never sees attacker-controlled
// markup that DOMPurify stripped.
//
// SRI hashes: there are no CDN deps — every dep is bundled by Next. The
// "SRI hashes preserved on CDN deps" clause in the issue is vacuously
// satisfied (no CDN load, no SRI to break).
//
// The single innerHTML call is annotated with `pi-lens-ignore` per the
// issue spec so a future DOMPurify-tightening audit can find it.

import { marked } from "marked";
import DOMPurify from "dompurify";
import Prism from "prismjs";
// Side-effect imports: Prism's per-language grammars. Each adds ~few KB and
// the markdown pipeline only needs a sensible default set; add more here
// when a chat payload actually starts quoting another language.
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-python";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-yaml";

marked.setOptions({
	gfm: true,
	breaks: true,
});

export function renderMarkdownSafe(source: string): string {
	// marked.parse can return a Promise when async extensions are present;
	// we use the synchronous form (no async extensions) and the signature
	// in marked@14 is overloaded — cast for the sync return.
	const html = marked.parse(source, { async: false }) as string;
	return DOMPurify.sanitize(html, {
		USE_PROFILES: { html: true },
		ADD_ATTR: ["target", "rel"],
	});
}

// Highlighter hook: walk a just-rendered bubble and color its <pre><code>
// blocks. Returns nothing (mutates the DOM in place) — the caller invokes
// it from a useLayoutEffect after the bubble mounts so the next paint
// already has the tokens. Safe to call repeatedly; Prism is idempotent
// for already-highlighted blocks.
export function highlightBubble(root: HTMLElement): void {
	try {
		Prism.highlightAllUnder(root);
	} catch {
		// Prism throws on truly malformed markup; the unsanitized version
		// would have been blocked by DOMPurify anyway, so a silent skip is
		// the right behavior.
	}
}
