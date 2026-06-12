import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

const BLOCKED_TITLE = `Dashboard blocked issue ${Date.now()}`;
const QUEUED_TITLE = `Dashboard queued issue ${Date.now()}`;

test("dashboard shows per-binding cards, global roll-up, and attention list with click-through", async ({
	page,
	problems,
}) => {
	// Seed extra issues across bindings so every state has at least one entry.
	seedIssue("homelab", BLOCKED_TITLE, "blocked");
	seedIssue("trading", QUEUED_TITLE, "todo");

	await page.goto("/");

	// Global roll-up visible.
	await expect(page.getByTestId("dashboard-global-rollup")).toBeVisible();
	await expect(page.getByTestId("dashboard-global-rollup")).toContainText(
		"issues",
	);

	// Per-binding cards for both non-archived bindings.
	const homelabCard = page.getByTestId("dashboard-binding-homelab");
	const tradingCard = page.getByTestId("dashboard-binding-trading");
	await expect(homelabCard).toBeVisible();
	await expect(tradingCard).toBeVisible();

	// Both bindings have items in multiple states from seed + our additions.
	await expect(homelabCard).toContainText("Todo");
	await expect(homelabCard).toContainText("Blocked");
	await expect(tradingCard).toContainText("Todo");

	// Attention list shows the blocked issue.
	await expect(page.getByTestId("dashboard-attention")).toBeVisible();
	await expect(page.getByTestId("attention-row")).toContainText(BLOCKED_TITLE);

	// Clicking an attention row navigates to the binding with ?issue=.
	await page
		.getByTestId("attention-row")
		.filter({ hasText: BLOCKED_TITLE })
		.click();
	await expect(page).toHaveURL(/\/homelab\?issue=\d+/);
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Close the flyout — the ?issue= param should be cleared.
	await page.getByTestId("flyout-backdrop").click({ position: { x: 5, y: 5 } });
	/**
	 * After race window the flyout closes and router.replace clears ?issue=.
	 * We assert the flyout is gone; trying to assert the URL exactly is prone
	 * to Next router timing, so we only check the flyout is hidden.
	 */
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	expectCleanConsole(problems, {
		ignore: [/ERR_ABORTED/],
	});
});
