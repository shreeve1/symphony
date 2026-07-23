import { expect, expectCleanConsole, test } from "./fixtures";

test("sidebar lists both bindings and navigates on click", async ({
	page,
	problems,
}) => {
	await page.goto("/");

	// Dashboard renders. Assert the two stable bindings render as sidebar rows.
	// Bindings come from live bindings.yml config, so more may exist (e.g. the
	// symphony self-binding); match by name rather than an exact count/order.
	await expect(page.getByTestId("dashboard-global-rollup")).toBeVisible();
	const rows = page.getByTestId("binding-row");
	await expect(rows.filter({ hasText: /^homelab$/ })).toHaveCount(1);
	await expect(rows.filter({ hasText: /^dotfiles$/ })).toHaveCount(1);

	// Clicking a binding navigates to /{binding} and shows the board.
	await page
		.getByTestId("binding-row")
		.filter({ hasText: /^homelab$/ })
		.click();
	await expect(page).toHaveURL("/homelab");
	await expect(page.getByRole("heading", { name: "homelab" })).toBeVisible();
	await expect(page.getByTestId("column-todo")).toBeVisible();

	expectCleanConsole(problems);
});
