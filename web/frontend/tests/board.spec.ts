import { STATES } from "../lib/issues";
import { expect, expectCleanConsole, test } from "./fixtures";

test("board renders state columns and opens a flyout on card click", async ({
	page,
	problems,
}) => {
	await page.goto("/trading");

	// Columns render in the fixed order declared by STATES.
	for (const state of STATES) {
		await expect(page.getByTestId(`column-${state.key}`)).toBeVisible();
	}

	// At least one issue card is visible (trading is seeded with two).
	await expect(page.getByTestId("issue-card").first()).toBeVisible();

	// Clicking the seed's running card opens the flyout.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Seed running issue for trading" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Clicking the backdrop (outside) closes it. Click the central strip of the
	// backdrop: the sidebar (z-50) sits above the z-40 backdrop on the left and
	// the flyout panel (~480px) covers the right, so {5,5} hits the sidebar.
	await page
		.getByTestId("flyout-backdrop")
		.click({ position: { x: 400, y: 360 } });
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	// Re-open the flyout: run history shows runs without any cost element.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Seed running issue for trading" })
		.click();
	await expect(page.getByTestId("run-row").first()).toBeVisible();
	await expect(page.getByTestId("run-cost")).toHaveCount(0);

	expectCleanConsole(problems);
});
