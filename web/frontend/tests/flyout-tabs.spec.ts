import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

test("flyout switches between Comments and Session tabs", async ({
	page,
	problems,
}) => {
	await page.goto("/trading");

	// Target the seeded issue by title to stay robust against extra seed data.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Seed running issue for trading" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// All seven metadata chips render (#013 added effort and base; priority and
	// max s were dropped from the flyout by operator request).
	const chips = page.getByTestId("metadata-chips").locator("> span");
	await expect(chips).toHaveCount(7);

	// Comments tab is selected by default; comments are AI-posted and render as
	// read-only formatted markdown, so assert on the rendered view text.
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"Replace with real operator thread",
	);

	// Switching to Session swaps in the steer composer + live session tail.
	await page.getByTestId("tab-session").click();
	await expect(page.getByTestId("tabpanel-session")).toBeVisible();

	// And back to Comments.
	await page.getByTestId("tab-comments").click();
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"Operator comments",
	);

	const flyout = page.getByTestId("issue-flyout");
	const normalWidth = (await flyout.boundingBox())?.width ?? 0;
	const viewportWidth = page.viewportSize()?.width ?? 0;
	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);
	const maximizedWidth = (await flyout.boundingBox())?.width ?? 0;
	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeCloseTo(normalWidth, 0);
	const restoredWidth = (await flyout.boundingBox())?.width ?? 0;
	expect(restoredWidth).toBeLessThan(maximizedWidth);

	expectCleanConsole(problems);
});

test("flyout maximize preference follows close, reopen, issue switches, and reloads", async ({
	page,
	problems,
}) => {
	const first = seedIssue("trading", "Flyout maximize memory A", "in_review");
	const second = seedIssue("trading", "Flyout maximize memory B", "blocked");

	await page.goto("/trading");
	await page.evaluate(() => {
		window.localStorage.removeItem("podium-flyout-maximized");
	});
	await page.goto(`/trading?issue=${first.issueId}`);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory A",
	);
	const flyout = page.getByTestId("issue-flyout");
	const viewportWidth = page.viewportSize()?.width ?? 0;
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);

	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.reload();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory A",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.getByTestId("close-issue-flyout").click();
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Flyout maximize memory A" })
		.click();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory A",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.goto(`/trading?issue=${second.issueId}`);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory B",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeLessThan(viewportWidth - 50);

	await page.reload();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory B",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeLessThan(viewportWidth - 50);

	await page.getByTestId("close-issue-flyout").click();
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Flyout maximize memory B" })
		.click();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory B",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeLessThan(viewportWidth - 50);

	expectCleanConsole(problems);
});
