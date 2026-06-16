"use client";

import { loader } from "@monaco-editor/react";

// Self-host Monaco from public/monaco/vs (copied from node_modules/monaco-editor/min/vs
// via `pnpm copy:monaco`). Podium sits behind Authelia; no runtime CDN dependency.
let configured = false;

export function setupMonaco() {
	if (configured) return;
	configured = true;
	loader.config({ paths: { vs: "/monaco/vs" } });
}
