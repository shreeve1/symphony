import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

// Attachment golden path (#325). Runs against throwaway e2e repos only.
// The last test asserts that live binding repos were never touched.

test("upload, list, download link, delete attachment", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue(
		"homelab",
		"Attachment upload test",
		"in_review",
	);
	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Attachment upload test",
	);

	// Switch to attachments tab
	await page.getByTestId("tab-attachments").click();
	await expect(page.getByTestId("tabpanel-attachments")).toBeVisible();

	// Empty state
	await expect(page.getByTestId("attachment-panel")).toContainText(
		"No attachments yet.",
	);

	// Upload a file via the hidden file input
	await page.setInputFiles('[data-testid="attachment-file-input"]', {
		name: "hello.txt",
		mimeType: "text/plain",
		buffer: Buffer.from("Hello, Symphony!"),
	});

	// Wait for the attachment to appear in the list (pending → settled)
	await expect(page.getByTestId("attachment-list")).toBeVisible();
	await expect(
		page.getByTestId("attachment-list").getByText("hello.txt"),
	).toBeVisible({ timeout: 10_000 });
	await expect(
		page.getByTestId("attachment-list").getByText("text/plain"),
	).toBeVisible();

	// Download link exists
	const downloadLink = page.getByTestId(/attachment-download-\d+/).first();
	await expect(downloadLink).toBeVisible();
	const href = await downloadLink.getAttribute("href");
	expect(href).toContain(`/api/issues/${issueId}/attachments/`);

	// Delete the attachment
	const deleteBtn = page.getByTestId(/attachment-delete-\d+/).first();
	await expect(deleteBtn).toBeVisible();
	await deleteBtn.click();

	// Back to empty state
	await expect(page.getByTestId("attachment-panel")).toContainText(
		"No attachments yet.",
	);

	expectCleanConsole(problems);
});

test("image file shows preview, drag-and-drop upload", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue(
		"dotfiles",
		"Attachment image preview test",
		"in_review",
	);
	await page.goto(`/dotfiles?issue=${issueId}`);
	await page.getByTestId("tab-attachments").click();
	await expect(page.getByTestId("tabpanel-attachments")).toBeVisible();

	// Upload a tiny PNG via file input
	// 1×1 pixel red PNG (valid minimal image)
	const png = Buffer.from(
		"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
		"base64",
	);
	await page.setInputFiles('[data-testid="attachment-file-input"]', {
		name: "pixel.png",
		mimeType: "image/png",
		buffer: png,
	});
	await expect(
		page.getByTestId("attachment-list").getByText("pixel.png"),
	).toBeVisible({ timeout: 10_000 });
	await expect(
		page.getByTestId("attachment-list").getByText("image/png"),
	).toBeVisible();

	// Image preview <img> exists with a src attrib
	const img = page.locator('[data-testid^="attachment-row-"] img').first();
	await expect(img).toBeVisible();
	const src = await img.getAttribute("src");
	expect(src).toContain(`/api/issues/${issueId}/attachments/`);

	expectCleanConsole(problems);
});

// Safety: live binding repos must not have any attachment files written
// during e2e. The API server only sees the throwaway bindings, so this is
// a structural invariant, not a probabilistic one.
test("live binding repos are not dirtied", () => {
	const bindingsPath = path.resolve(__dirname, "../../../bindings.yml");
	const repoRoot = path.resolve(__dirname, "../../..");
	const script = [
		"import json",
		"import yaml",
		"from pathlib import Path",
		"",
		`bindings_path = Path(${JSON.stringify(bindingsPath)})`,
		"data = yaml.safe_load(bindings_path.read_text(encoding='utf-8')) or {}",
		"leaks = []",
		"for b in data.get('bindings') or []:",
		"    att_dir = Path(b['repo_path']) / '.symphony' / 'attachments'",
		"    try:",
		"        is_dir = att_dir.is_dir()",
		"    except PermissionError:",
		"        continue",
		"    if not is_dir:",
		"        continue",
		"    for child in att_dir.iterdir():",
		"        if child.is_file():",
		"            leaks.append(str(child))",
		"        elif child.is_dir():",
		"            for sub in child.iterdir():",
		"                if sub.is_file():",
		"                    leaks.append(str(sub))",
		"print(json.dumps({'leaks': leaks}))",
	].join("\n");
	const result = execFileSync("uv", ["run", "python", "-c", script], {
		cwd: repoRoot,
		stdio: "pipe",
	});
	const { leaks } = JSON.parse(result.toString()) as { leaks: string[] };
	expect(leaks, `live repos dirtied:\n${leaks.join("\n")}`).toEqual([]);
});
