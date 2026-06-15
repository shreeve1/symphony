import { expect, expectCleanConsole, test } from "./fixtures";

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
