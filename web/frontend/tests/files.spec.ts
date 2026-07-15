import { expect, expectCleanConsole, test } from "./fixtures";

// File browser/editor golden path (T.3.1 + T.3.2). Runs ONLY against the
// homelab binding's THROWAWAY repo (test-results/e2e-repos/homelab, seeded by
// tests/global-setup.mjs) — never the live /home/james/homelab.
//
// Monaco is self-hosted (lib/monaco.ts). This spec also asserts the editor
// pulls nothing from a CDN host at runtime.
const CDN_HOSTS = ["cdn.jsdelivr.net", "unpkg.com"];

test("browse, expand, open, edit, save, persist; no Monaco CDN", async ({
	page,
	problems,
}) => {
	const cdnHits: string[] = [];
	page.on("request", (req) => {
		const url = req.url();
		if (CDN_HOSTS.some((host) => url.includes(host))) {
			cdnHits.push(url);
		}
	});

	await page.goto("/homelab/files");

	// Tree root lists the seeded entries.
	await expect(page.getByTestId("file-browser")).toBeVisible();
	const docsDir = page.getByTestId("dir-row").filter({ hasText: "docs" });
	await expect(docsDir).toBeVisible();

	// T.3.1: expand docs/ → its child file lazy-loads.
	await docsDir.click();
	const nestedFile = page
		.getByTestId("file-row")
		.filter({ hasText: "note.md" });
	await expect(nestedFile).toBeVisible();

	// Open the root sample.md and wait for Monaco to mount with its content.
	await page.getByTestId("file-row").filter({ hasText: "sample.md" }).click();
	await page.waitForSelector(".monaco-editor");
	await expect(page.locator(".monaco-editor")).toContainText("# sample");

	// T.3.2: replace the content via Monaco, then save.
	const newContent = `# edited ${Date.now()}`;
	// Focus the editor by clicking its content area, then select-all + retype.
	// (The hidden .ime-text-area textarea is covered by view-lines and can't be
	// clicked directly.)
	await page.locator(".monaco-editor .view-lines").click();
	await page.keyboard.press(
		process.platform === "darwin" ? "Meta+A" : "Control+A",
	);
	await page.keyboard.type(newContent);

	const saved = page.waitForResponse(
		(res) =>
			res.url().includes("/api/bindings/homelab/files/content") &&
			res.request().method() === "PUT" &&
			res.ok(),
	);
	await page.getByTestId("file-save").click();
	await saved;

	// Reload, reopen the file: the edit persisted to the throwaway repo on disk.
	await page.reload();
	await page.getByTestId("file-row").filter({ hasText: "sample.md" }).click();
	await page.waitForSelector(".monaco-editor");
	await expect(page.locator(".monaco-editor")).toContainText(newContent);

	// Monaco self-hosting: zero CDN requests.
	expect(
		cdnHits,
		`unexpected Monaco CDN requests:\n${cdnHits.join("\n")}`,
	).toEqual([]);
	expectCleanConsole(problems);
});

test("new file into clicked folder, then delete it", async ({
	page,
	problems,
}) => {
	await page.goto("/homelab/files");
	await expect(page.getByTestId("file-browser")).toBeVisible();

	const fname = `e2e-${Date.now()}.md`;

	// Click docs/ → it becomes the create target (and expands).
	await page.getByTestId("dir-row").filter({ hasText: "docs" }).click();

	// New → prompt asks for a filename; answer with our name.
	page.once("dialog", (d) => d.accept(fname));
	const created = page.waitForResponse(
		(res) =>
			res.url().includes("/api/bindings/homelab/files") &&
			res.request().method() === "POST" &&
			res.ok(),
	);
	await page.getByTestId("file-new").click();
	await created;

	// New file appears under docs/ and auto-opens in the editor.
	const newRow = page.getByTestId("file-row").filter({ hasText: fname });
	await expect(newRow).toBeVisible();
	await page.waitForSelector(".monaco-editor");

	// Delete → confirm dialog; row disappears and editor returns to empty state.
	page.once("dialog", (d) => d.accept());
	const deleted = page.waitForResponse(
		(res) =>
			res.url().includes("/api/bindings/homelab/files/content") &&
			res.request().method() === "DELETE" &&
			res.ok(),
	);
	await page.getByTestId("file-delete").click();
	await deleted;
	await expect(newRow).toHaveCount(0);
	await expect(page.getByTestId("file-editor-empty")).toBeVisible();

	expectCleanConsole(problems);
});

test("expand toggle hides tree, restores it, persists across reload", async ({
	page,
	problems,
}) => {
	// Wipe the key once on first navigation. (`addInitScript` would re-clear
	// it on every reload and defeat the persistence half of this test.)
	await page.goto("/homelab/files");
	await page.evaluate(() => {
		try {
			window.localStorage.removeItem("podium-files-expanded");
		} catch {
			/* ignore */
		}
	});
	await page.reload();

	const tree = page.getByTestId("files-tree");
	await expect(tree).toBeVisible();
	await expect(page.getByTestId("files-expand-toggle")).toHaveText("Maximize");

	// Toggle 1 → tree hidden, control stays in the same spot, label flips.
	await page.getByTestId("files-expand-toggle").click();
	await expect(page.getByTestId("files-expand-toggle")).toHaveText("Restore");
	await expect(tree).toBeHidden();

	// Toggle 2 → tree visible again, label flips back to Maximize.
	await page.getByTestId("files-expand-toggle").click();
	await expect(page.getByTestId("files-expand-toggle")).toHaveText("Maximize");
	await expect(tree).toBeVisible();

	// Persist: expand, reload, key survived.
	await page.getByTestId("files-expand-toggle").click();
	await expect(page.getByTestId("files-expand-toggle")).toHaveText("Restore");
	await page.reload();
	await expect(page.getByTestId("files-expand-toggle")).toHaveText("Restore");
	await expect(page.getByTestId("files-tree")).toBeHidden();

	// Cleanup so other tests don't inherit the persisted true.
	await page.evaluate(() => {
		try {
			window.localStorage.removeItem("podium-files-expanded");
		} catch {
			/* ignore */
		}
	});

	expectCleanConsole(problems);
});
