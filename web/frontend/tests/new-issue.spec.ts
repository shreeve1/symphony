import { expect, expectCleanConsole, test } from "./fixtures";

// Runs against /homelab so the /dotfiles seeds that board.spec asserts on stay
// pristine. Unique title per run: the dev database persists across runs.
test("new issue flow: modal -> Todo card -> survives reload", async ({
	page,
	problems,
}) => {
	const desc = `e2e new issue ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	await page.getByTestId("new-issue-description").fill(desc);
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
			.filter({ hasText: "gpt-5.6-sol" }),
	).toBeVisible();
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-model").click();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "Opus 4.8 (claude-opus-4-8)" }),
	).toBeVisible();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "gpt-5.6-sol" }),
	).toHaveCount(0);
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-model").click();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "gpt-5.6-sol" }),
	).toBeVisible();
	await expect(
		page
			.getByTestId("new-issue-model-option")
			.filter({ hasText: "Opus 4.8 (claude-opus-4-8)" }),
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
	await page.route("**/api/skills?binding=homelab", (route) =>
		route.fulfill({
			contentType: "application/json",
			body: JSON.stringify([{ name: "alpha" }, { name: "beta" }]),
		}),
	);
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
		await new Promise((resolve) => setTimeout(resolve, 1_000));
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
		.filter({ hasText: "Generating title..." });
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

	// Select pi → model preselects the current pi default.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("Duo");

	// Switch to claude → model preselects claude default (Opus 4.8).
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue(
		"Opus 4.8 (claude-opus-4-8)",
	);

	// Switch back to pi → model restores pi default.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("Duo");

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

test("slash picker commits a keyboard selection without changing description prose", async ({
	page,
	problems,
}) => {
	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	const description = page.getByTestId("new-issue-description");

	await description.fill("Keep /srv/app and https://example.test/a literal /ho");
	await expect(description).toHaveAttribute("role", "combobox");
	await expect(description).toHaveAttribute("aria-expanded", "true");
	await expect(page.getByRole("listbox", { name: "Issue fields" })).toBeVisible();
	await expect(page.getByRole("option", { name: "Hold" })).toBeVisible();
	await page.keyboard.press("Tab");
	await expect(page.getByRole("listbox", { name: "Hold values" })).toBeVisible();
	await page.keyboard.type("yes");
	await page.keyboard.press("Enter");

	await expect(page.getByTestId("new-issue-hold")).toBeChecked();
	await expect(description).toHaveValue(
		"Keep /srv/app and https://example.test/a literal ",
	);
	await expect(description).toHaveAttribute("aria-expanded", "false");
	await page.keyboard.type("after");
	await expect(description).toHaveValue(
		"Keep /srv/app and https://example.test/a literal after",
	);

	expectCleanConsole(problems);
});

test("slash picker filters accessibly, supports arrows, pointer, and Escape", async ({
	page,
	problems,
}) => {
	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	const description = page.getByTestId("new-issue-description");

	await description.fill("path/to/file https://example.test/a prefix/hold");
	await expect(description).toHaveAttribute("aria-expanded", "false");

	await description.fill("prefix /");
	const fields = page.getByRole("listbox", { name: "Issue fields" });
	await expect(fields).toBeVisible();
	const activeId = await description.getAttribute("aria-activedescendant");
	expect(activeId).toBeTruthy();
	await expect(page.locator(`#${activeId}`)).toHaveAttribute(
		"aria-selected",
		"true",
	);
	await page.keyboard.press("ArrowDown");
	await page.keyboard.press("ArrowUp");
	await page.keyboard.press("Escape");
	await expect(description).toHaveAttribute("aria-expanded", "false");
	await expect(description).toHaveValue("prefix /");
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	await description.fill("prefix /hold");
	await page.keyboard.press("Tab");
	await expect(page.getByRole("listbox", { name: "Hold values" })).toBeVisible();
	await page.keyboard.press("Backspace");
	await expect(page.getByRole("listbox", { name: "Issue fields" })).toBeVisible();
	await page.keyboard.press("Escape");

	await description.fill("prefix /hold");
	await page.getByRole("option", { name: "Hold" }).click();
	await page.getByRole("option", { name: "Yes" }).click();
	await expect(page.getByTestId("new-issue-hold")).toBeChecked();
	await expect(description).toHaveValue("prefix ");

	expectCleanConsole(problems);
});

test("slash picker preserves dependencies, clearing, free text, multiple commands, and Create", async ({
	page,
	problems,
}) => {
	await page.route("**/api/bindings/homelab/options", async (route) => {
		const response = await route.fetch();
		await route.fulfill({
			response,
			json: {
				agents: ["pi", "claude"],
				models: [
					{
						id: "pi-small",
						agent: "pi",
						default: true,
						efforts: ["low", "high"],
					},
					{
						id: "pi-wide",
						agent: "pi",
						efforts: ["none", "medium"],
					},
					{ id: "claude-a", agent: "claude", default: true },
				],
				branches: ["main", "release"],
			},
		});
	});
	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	const description = page.getByTestId("new-issue-description");
	await page.getByTestId("new-issue-agent").click();
	await expect(
		page.getByTestId("new-issue-agent-option").filter({ hasText: "pi" }),
	).toBeVisible();
	await description.fill("Keep /srv/app and https://example.test/a: ");

	await page.keyboard.type("/ag");
	await page.keyboard.press("Tab");
	await page.keyboard.type("PI");
	await page.keyboard.press("Tab");
	await expect(page.getByTestId("new-issue-agent")).toHaveValue("pi");
	await expect(page.getByTestId("new-issue-model")).toHaveValue("pi-small");

	await page.keyboard.type("/eff");
	await page.keyboard.press("Tab");
	await page.keyboard.type("high");
	await expect(
		page.getByRole("listbox", { name: "Effort values" }).getByRole("option", {
			name: "high",
			exact: true,
		}),
	).toBeVisible();
	await page.keyboard.press("Enter");
	await expect(description).not.toHaveValue(/\/Effort/);
	await expect(page.getByTestId("new-issue-effort")).toHaveValue("high");

	await page.keyboard.type("/mod");
	await page.keyboard.press("Tab");
	await expect(page.getByRole("option", { name: "pi-wide" })).toBeVisible();
	await expect(page.getByRole("option", { name: "claude-a" })).toHaveCount(0);
	await page.keyboard.type("wide");
	await page.keyboard.press("Tab");
	await expect(page.getByTestId("new-issue-model")).toHaveValue("pi-wide");
	await expect(page.getByTestId("new-issue-effort")).toHaveValue("");

	await page.keyboard.type("/eff");
	await page.keyboard.press("Tab");
	await expect(page.getByRole("option", { name: "medium" })).toBeVisible();
	await expect(
		page.getByRole("option", { name: "high", exact: true }),
	).toHaveCount(0);
	await page.keyboard.type("medium");
	await page.keyboard.press("Tab");

	await page.keyboard.type("/eff");
	await page.keyboard.press("Tab");
	await page.keyboard.press("Tab");
	await expect(page.getByTestId("new-issue-effort")).toHaveValue("");
	await page.keyboard.type("/eff");
	await page.keyboard.press("Tab");
	await page.keyboard.type("medium");
	await page.keyboard.press("Tab");

	await page.keyboard.type("/base");
	await page.keyboard.press("Tab");
	await page.keyboard.type("custom-branch");
	await page.keyboard.press("Enter");
	await expect(page.getByTestId("new-issue-base")).toHaveValue("custom-branch");

	await page.keyboard.type("/hold");
	await page.keyboard.press("Tab");
	await page.keyboard.type("yes");
	await page.keyboard.press("Tab");
	await expect(page.getByTestId("new-issue-hold")).toBeChecked();
	await page.keyboard.type("/hold");
	await page.keyboard.press("Tab");
	await page.keyboard.type("no");
	await page.keyboard.press("Tab");
	await expect(page.getByTestId("new-issue-hold")).not.toBeChecked();

	await page.keyboard.type("done");
	await expect(description).toHaveValue(
		"Keep /srv/app and https://example.test/a: done",
	);
	const request = page.waitForRequest(
		(req) =>
			req.url().includes("/api/bindings/homelab/issues") &&
			req.method() === "POST",
	);
	await page.getByTestId("new-issue-submit").click();
	const body = (await request).postDataJSON();
	expect(body).toMatchObject({
		description: "Keep /srv/app and https://example.test/a: done",
		preferred_agent: "pi",
		preferred_model: "pi-wide",
		reasoning_effort: "medium",
		base_branch: "custom-branch",
	});
	expect(body).not.toHaveProperty("preferred_skill");
	expect(body).not.toHaveProperty("hold");
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();

	expectCleanConsole(problems);
});

test("slash picker exposes Schedule only for infra bindings", async ({
	page,
	problems,
}) => {
	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	const description = page.getByTestId("new-issue-description");
	await description.fill("Schedule me /sche");
	await page
		.getByRole("option", { name: "Schedule for next maintenance window" })
		.click();
	await page
		.getByRole("listbox", { name: "Schedule for next maintenance window values" })
		.getByRole("option", { name: "Yes" })
		.click();
	await expect(page.getByTestId("new-issue-schedule-mode")).toHaveValue(
		"next_window",
	);
	await page.getByText("Cancel", { exact: true }).click();

	await page.goto("/dotfiles");
	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-description").fill("No schedule /sche");
	await expect(
		page.getByRole("option", { name: "Schedule for next maintenance window" }),
	).toHaveCount(0);
	await expect(page.getByText("No matches", { exact: true })).toBeVisible();

	expectCleanConsole(problems);
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

	// pi has a default → preselects Duo.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("Duo");

	// claude has no default → model clears to placeholder.
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("");

	// Switch back to pi → pi default restores.
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-description").click();
	await expect(page.getByTestId("new-issue-model")).toHaveValue("Duo");

	expectCleanConsole(problems);
});
