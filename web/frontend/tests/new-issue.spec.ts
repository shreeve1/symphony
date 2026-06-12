import { expect, expectCleanConsole, seedSkills, test } from "./fixtures";

// Runs against /homelab so the /trading seeds that board.spec asserts on stay
// pristine. Unique title per run: the dev database persists across runs.
test("new issue flow: modal -> Todo card -> survives reload", async ({
	page,
	problems,
}) => {
	seedSkills([{ name: "diagnose", description: "Diagnose e2e fixture" }]);
	const title = `e2e new issue ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();

	await page.getByTestId("new-issue-title").fill(title);
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
		.filter({ hasText: title });
	await expect(todoCard).toBeVisible();
	await created;

	// Reload: the card persisted through SQLite, optional fields included.
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
	const title = `e2e custom model ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-title").fill(title);

	await page.getByTestId("new-issue-model").click();
	await expect(
		page.getByTestId("new-issue-model-option").filter({ hasText: "glm-5.1:high" }),
	).toBeVisible();
	await page.getByTestId("new-issue-agent").fill("claude");
	await page.getByTestId("new-issue-model").click();
	await expect(
		page.getByTestId("new-issue-model-option").filter({ hasText: "claude-fable-5" }),
	).toBeVisible();
	await expect(
		page.getByTestId("new-issue-model-option").filter({ hasText: "glm-5.1:high" }),
	).toHaveCount(0);
	await page.getByTestId("new-issue-agent").fill("pi");
	await page.getByTestId("new-issue-model").click();
	await expect(
		page.getByTestId("new-issue-model-option").filter({ hasText: "glm-5.1:high" }),
	).toBeVisible();
	await expect(
		page.getByTestId("new-issue-model-option").filter({ hasText: "claude-fable-5" }),
	).toHaveCount(0);

	await page.getByTestId("new-issue-agent").fill("custom-agent");
	await page.getByTestId("new-issue-model").fill("custom-model");
	await page.getByTestId("new-issue-skill").fill("not-a-skill");
	await page.getByTestId("new-issue-title").focus();
	await expect(page.getByTestId("new-issue-skill")).toHaveValue("");

	await page.getByTestId("new-issue-submit").click();
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();
	const todoCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: title });
	await expect(todoCard).toBeVisible();
	await todoCard.click();
	await expect(page.getByTestId("edit-preferred_agent")).toHaveValue("custom-agent");
	await expect(page.getByTestId("edit-preferred_model")).toHaveValue("custom-model");

	expectCleanConsole(problems);
});

test("create failure rolls back the card and keeps the modal open", async ({
	page,
	problems,
}) => {
	const title = `e2e doomed issue ${Date.now()}`;

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
	await page.getByTestId("new-issue-title").fill(title);
	await page.getByTestId("new-issue-submit").click();

	// Optimistic card appears immediately…
	const doomedCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: title });
	await expect(doomedCard).toBeVisible();

	// …then rolls back when the 422 lands; the modal stays open with the typed
	// title intact and an error line, so nothing is silently lost.
	await expect(doomedCard).toHaveCount(0);
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();
	await expect(page.getByTestId("new-issue-error")).toBeVisible();
	await expect(page.getByTestId("new-issue-title")).toHaveValue(title);

	expectCleanConsole(problems, { ignore: [/422/] });
});
