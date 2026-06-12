import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

const QUEUED_TITLE = `Dashboard queued issue ${Date.now()}`;

test("dashboard shows per-binding cards and global roll-up", async ({
	page,
	problems,
}) => {
	// Seed an extra issue so the dashboard has fresh data to roll up.
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

	await expect(page.getByTestId("dashboard-attention")).toHaveCount(0);
	await expect(page.getByTestId("attention-row")).toHaveCount(0);

	expectCleanConsole(problems, {
		ignore: [/ERR_ABORTED/],
	});
});
