import { expect, expectCleanConsole, seedSkills, test } from "./fixtures";

// Runs against /homelab so the /dotfiles seeds that board.spec asserts on stay
// pristine. Unique title per run: the dev database persists across runs.
test("new issue flow: modal -> Todo card -> survives reload", async ({
	page,
	problems,
}) => {
	seedSkills([{ name: "diagnose", description: "Diagnose e2e fixture" }]);
	const desc = `e2e new issue ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	await page.getByTestId("new-issue-description").fill(desc);
	// Pick a skill from the seeded catalog (FK-validated server side).
	await page.getByTestId("new-issue-skill").fill("diag");
	await page
		.getByTestId("new-issue-skill-option")
		.filter({ hasText: "diagnose" })
		.click();
	// Optional flyout-parity fields flow through to the created row.
	await page.getByTestId("new-issue-effort").fill("low");
	await page
		.getByTestId("new-issue-effort-option")
		.filter({ hasText: "low" })
		.click();
	await page.getByTestId("new-issue-agent").fill("pi");

	const created = page.waitForResponse(
		(res) =>
			res.url().includes("/api/bindings/homelab/issues") &&
			res.request().method() === "POST" &&
			res.status() === 201,
	);
	await page.getByTestId("new-issue-submit").click();

	// Modal closes once the POST succeeds; the optimistic card lands in Todo.
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();
	const todoCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: desc });
	await expect(todoCard).toBeVisible();
	await created;
	await page.reload();
	await expect(todoCard).toBeVisible();
	await todoCard.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("edit-reasoning_effort")).toHaveValue("low");
	await expect(page.getByTestId("edit-preferred_agent")).toHaveValue("pi");

	expectCleanConsole(problems);
});

test("new issue combobox filters models and preserves free-text agent/model", async ({
	page,
	problems,
}) => {
	const desc = `e2e custom model ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-description").fill(desc);

	await page.getByTestId("new-issue-model").click();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "gpt-5.3-codex-spark" }),
	).toBeVisible();
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-model").click();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "claude-fable-5" }),
	).toBeVisible();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "gpt-5.3-codex-spark" }),
	).toHaveCount(0);
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-model").click();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "gpt-5.3-codex-spark" }),
	).toBeVisible();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "claude-fable-5" }),
	).toHaveCount(0);

	await page.getByTestId("new-issue-agent").fill("custom-agent");
	await page.getByTestId("new-issue-model").fill("custom-model");
	await page.getByTestId("new-issue-skill").fill("not-a-skill");
	await page.getByTestId("new-issue-description").focus();
	await expect(page.getByTestId("new-issue-skill")).toHaveValue("");

	await page.getByTestId("new-issue-submit").click();
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();
	const todoCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: desc });
	await expect(todoCard).toBeVisible();
	await todoCard.click();
	await expect(page.getByTestId("edit-preferred_agent")).toHaveValue(
		"custom-agent",
	);
	await expect(page.getByTestId("edit-preferred_model")).toHaveValue(
		"custom-model",
	);

	expectCleanConsole(problems);
});

test("combobox arrow keys highlight and Enter selects; Escape closes only the popup", async ({
	page,
	problems,
}) => {
	seedSkills([
		{ name: "alpha", description: "first" },
		{ name: "beta", description: "second" },
	]);

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	// Open the skill combobox and walk down with the arrow key: index 0 is the
	// empty "—" row, index 1 is the first real option (alpha).
	await page.getByTestId("new-issue-skill").click();
	await expect(
		page.getByTestId("new-issue-skill-option").first(),
	).toBeVisible();
	await page.keyboard.press("ArrowDown");
	await page.keyboard.press("ArrowDown");
	await page.keyboard.press("Enter");
	await expect(page.getByTestId("new-issue-skill")).toHaveValue("alpha");

	// ArrowDown reopens the closed popup (input keeps focus after selection);
	// Escape then closes only the popup, leaving the modal open.
	await page.keyboard.press("ArrowDown");
	await expect(
		page.getByTestId("new-issue-skill-option").first(),
	).toBeVisible();
	await page.keyboard.press("Escape");
	await expect(page.getByTestId("new-issue-skill-option")).toHaveCount(0);
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	expectCleanConsole(problems);
});

test("create failure rolls back the card and keeps the modal open", async ({
	page,
	problems,
}) => {
	const desc = `e2e doomed issue ${Date.now()}`;

	await page.goto("/homelab");
	await page.route("**/api/bindings/homelab/issues", async (route) => {
		if (route.request().method() !== "POST") return route.fallback();
		// Delay the failure so the optimistic card is observable first.
		await new Promise((resolve) => setTimeout(resolve, 400));
		return route.fulfill({
			status: 422,
			contentType: "application/json",
			body: JSON.stringify({ detail: "stubbed failure" }),
		});
	});

	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-description").fill(desc);
	await page.getByTestId("new-issue-submit").click();

	// Optimistic card appears immediately…
	const doomedCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: desc });
	await expect(doomedCard).toBeVisible();

	// …then rolls back when the 422 lands; the modal stays open with the typed
	// title intact and an error line, so nothing is silently lost.
	await expect(doomedCard).toHaveCount(0);
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();
	await expect(page.getByTestId("new-issue-error")).toBeVisible();
	await expect(page.getByTestId("new-issue-description")).toHaveValue(desc);

	expectCleanConsole(problems, { ignore: [/422/] });
});

test("agent-aware model preselect switches default with agent", async ({
	page,
	problems,
}) => {
	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	// Agent field starts empty → no default preselected.
	await page.getByTestId("new-issue-model").click();
	await expect(page.getByTestId("new-issue-model-option").first()).toHaveText(
		/^—/,
	);
	await page.getByTestId("new-issue-model").blur();

	// Select pi → model preselects pi default (gpt-5.5).
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("gpt-5.5");

	// Switch to claude → model preselects claude default (Opus 4.8).
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue(
		"Opus 4.8 (claude-opus-4-8)",
	);

	// Switch back to pi → model restores pi default.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("gpt-5.5");

	expectCleanConsole(problems);
});

test("create with attachment holds through upload then releases", async ({
	page,
	problems,
}) => {
	const desc = `e2e attach issue ${Date.now()}`;
	const fileName = "e2e-attach.txt";

	await page.goto("/dotfiles");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	await page.getByTestId("new-issue-description").fill(desc);

	// Stage a file
	await page.setInputFiles('[data-testid="new-issue-file-input"]', {
		name: fileName,
		mimeType: "text/plain",
		buffer: Buffer.from("e2e staged content"),
	});
	await expect(
		page.getByTestId("new-issue-staged-files").getByText(fileName),
	).toBeVisible();

	const created = page.waitForResponse(
		(res) =>
			res.url().includes("/api/bindings/dotfiles/issues") &&
			res.request().method() === "POST" &&
			res.status() === 201,
	);
	const createRequest = page.waitForRequest(
		(req) =>
			req.url().includes("/api/bindings/dotfiles/issues") &&
			req.method() === "POST",
	);
	const releaseRequest = page.waitForRequest(
		(req) =>
			/\/api\/issues\/\d+$/.test(new URL(req.url()).pathname) &&
			req.method() === "PATCH",
	);
	await page.getByTestId("new-issue-submit").click();
	const [post, release] = await Promise.all([
		createRequest,
		releaseRequest,
		created,
	]);
	expect(post.postDataJSON()).toMatchObject({ hold: true });
	expect(release.postDataJSON()).toEqual({ hold: false });

	// Modal closes after upload succeeds and the issue is released.
	await expect(page.getByTestId("new-issue-modal")).toBeHidden({
		timeout: 10_000,
	});
	const todoCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: desc });
	await expect(todoCard).toBeVisible();

	// Open flyout, check attachments tab for uploaded file
	await todoCard.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await page.getByTestId("tab-attachments").click();
	await expect(page.getByTestId("tabpanel-attachments")).toBeVisible();
	await expect(
		page.getByTestId("attachment-list").getByText(fileName),
	).toBeVisible({ timeout: 10_000 });

	expectCleanConsole(problems);
});

test("partial attachment failure retries the same held issue", async ({
	page,
	problems,
}) => {
	const desc = `e2e attach retry ${Date.now()}`;
	const successfulFile = "already-uploaded.txt";
	const failedFile = "retry-me.txt";
	let createCount = 0;
	let createBody: Record<string, unknown> = {};
	let releaseCount = 0;
	let uploadCount = 0;
	const uploadAttempts: Record<string, number> = {
		[successfulFile]: 0,
		[failedFile]: 0,
	};

	await page.route("**/api/bindings/homelab/issues", async (route) => {
		if (route.request().method() === "POST") {
			createCount += 1;
			createBody = route.request().postDataJSON();
		}
		return route.fallback();
	});
	await page.route("**/api/issues/**", async (route) => {
		const request = route.request();
		const path = new URL(request.url()).pathname;
		if (request.method() === "POST" && /\/attachments$/.test(path)) {
			uploadCount += 1;
			const file = uploadCount === 1 ? successfulFile : failedFile;
			uploadAttempts[file] += 1;
			if (uploadCount === 2) {
				return route.fulfill({ status: 500, body: "stubbed failure" });
			}
		}
		if (request.method() === "PATCH" && /\/api\/issues\/\d+$/.test(path)) {
			releaseCount += 1;
			expect(request.postDataJSON()).toEqual({ hold: false });
		}
		return route.fallback();
	});

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-description").fill(desc);
	await page.setInputFiles('[data-testid="new-issue-file-input"]', [
		{
			name: successfulFile,
			mimeType: "text/plain",
			buffer: Buffer.from("uploaded once"),
		},
		{
			name: failedFile,
			mimeType: "text/plain",
			buffer: Buffer.from("retry this"),
		},
	]);

	await page.getByTestId("new-issue-submit").click();
	await expect(page.getByTestId("new-issue-upload-error")).toBeVisible();
	expect(createCount).toBe(1);
	expect(createBody).toMatchObject({ hold: true });
	expect(uploadAttempts).toEqual({
		[successfulFile]: 1,
		[failedFile]: 1,
	});
	await expect(
		page.getByTestId("new-issue-staged-files").getByText(successfulFile),
	).toHaveCount(0);
	await expect(
		page.getByTestId("new-issue-staged-files").getByText(failedFile),
	).toBeVisible();

	await page.getByTestId("new-issue-submit").click();
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();
	expect(createCount).toBe(1);
	expect(uploadAttempts).toEqual({
		[successfulFile]: 1,
		[failedFile]: 2,
	});
	expect(releaseCount).toBe(1);

	expectCleanConsole(problems, { ignore: [/500/] });
});

test("model preselect clears when agent has no default", async ({
	page,
	problems,
}) => {
	await page.goto("/homelab");

	// Intercept options to strip the claude default.
	await page.route("**/api/bindings/homelab/options", async (route) => {
		const response = await route.fetch();
		const body = await response.json();
		body.models = body.models.map((m: Record<string, unknown>) =>
			m.agent === "claude" ? { ...m, default: false } : m,
		);
		await route.fulfill({ response, json: body });
	});

	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	// pi has a default → preselects gpt-5.5.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("gpt-5.5");

	// claude has no default → model clears to placeholder.
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("");

	// Switch back to pi → pi default restores.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("gpt-5.5");

	expectCleanConsole(problems);
});
