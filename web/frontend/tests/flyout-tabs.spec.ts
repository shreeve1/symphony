import { expect, expectCleanConsole, test } from "./fixtures";

test("flyout switches between Comments and Context tabs", async ({
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

	// Switching to Context shows the seeded context_md instead (also rendered).
	await page.getByTestId("tab-context").click();
	await expect(page.getByTestId("view-context_md")).toContainText(
		"Synthetic context for",
	);

	// And back to Comments.
	await page.getByTestId("tab-comments").click();
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"Operator comments",
	);

	expectCleanConsole(problems);
});
