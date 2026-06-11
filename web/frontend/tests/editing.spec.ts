import type { Page } from "@playwright/test";

import { expect, expectCleanConsole, seedSkills, test } from "./fixtures";

// Both tests run against /homelab so the /trading seeds that board.spec and
// flyout-tabs.spec assert on stay pristine. Each test uses its own card —
// they run in parallel against the same persistent dev database.
const PERSIST_CARD = "Seed todo issue for homelab";
const REVERT_CARD = "Seed running issue for homelab";

async function openIssue(page: Page, title: string) {
	await page.goto("/homelab");
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
}

const waitForPatch = (page: Page) =>
	page.waitForResponse(
		(res) =>
			res.url().includes("/api/issues/") &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

// Edits target whichever value the field does NOT currently hold, so the test
// is idempotent against a database that already absorbed a previous run.
test("typed column and comments edits persist across reload", async ({
	page,
	problems,
}) => {
	seedSkills([
		{ name: "tdd", description: "TDD e2e fixture" },
		{ name: "code-review", description: "Review e2e fixture" },
	]);
	await openIssue(page, PERSIST_CARD);

	// state chip (select)
	const state = page.getByTestId("edit-state");
	const nextState =
		(await state.inputValue()) === "blocked" ? "todo" : "blocked";
	let patched = waitForPatch(page);
	await state.selectOption(nextState);
	await patched;

	// preferred_skill chip (select fed by the seeded skill catalog)
	const skill = page.getByTestId("edit-preferred_skill");
	const nextSkill =
		(await skill.inputValue()) === "tdd" ? "code-review" : "tdd";
	patched = waitForPatch(page);
	await skill.selectOption(nextSkill);
	await patched;

	// worktree toggle
	const worktree = page.getByTestId("edit-worktree_active");
	const wasActive = (await worktree.getAttribute("aria-pressed")) === "true";
	patched = waitForPatch(page);
	await worktree.click();
	await patched;

	// comments_md editor (textarea, commits on blur)
	const marker = `e2e edit marker ${Date.now()}`;
	const comments = page.getByTestId("edit-comments_md");
	await comments.fill(`# Operator comments\n\n${marker}`);
	patched = waitForPatch(page);
	await comments.blur();
	await patched;

	// Close, reload, reopen: every edit persisted through SQLite.
	await page.keyboard.press("Escape");
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await page.reload();
	await page
		.getByTestId("issue-card")
		.filter({ hasText: PERSIST_CARD })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	await expect(page.getByTestId("edit-state")).toHaveValue(nextState);
	await expect(page.getByTestId("edit-preferred_skill")).toHaveValue(nextSkill);
	await expect(page.getByTestId("edit-worktree_active")).toHaveAttribute(
		"aria-pressed",
		String(!wasActive),
	);
	await expect(page.getByTestId("edit-comments_md")).toHaveValue(
		new RegExp(marker),
	);

	expectCleanConsole(problems);
});

test("optimistic chip edit reverts when the API rejects it", async ({
	page,
	problems,
}) => {
	await openIssue(page, REVERT_CARD);

	await page.route("**/api/issues/*", async (route) => {
		if (route.request().method() !== "PATCH") return route.fallback();
		// Delay the failure so the optimistic value is observable first.
		await new Promise((resolve) => setTimeout(resolve, 400));
		return route.fulfill({
			status: 422,
			contentType: "application/json",
			body: JSON.stringify({ detail: "stubbed failure" }),
		});
	});

	const state = page.getByTestId("edit-state");
	const before = await state.inputValue();
	const attempted = before === "blocked" ? "todo" : "blocked";
	await state.selectOption(attempted);

	// Optimistic update shows immediately…
	await expect(state).toHaveValue(attempted);
	// …then the chip reverts when the 422 lands.
	await expect(state).toHaveValue(before);

	expectCleanConsole(problems, { ignore: [/422/] });
});
