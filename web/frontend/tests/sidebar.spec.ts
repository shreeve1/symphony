import { expect, expectCleanConsole, test } from "./fixtures";

test("sidebar lists both bindings and navigates on click", async ({
	page,
	problems,
}) => {
	await page.goto("/");

	// Dashboard renders. Both seeded bindings render as sidebar rows.
	await expect(page.getByTestId("dashboard-global-rollup")).toBeVisible();
	const rows = page.getByTestId("binding-row");
	await expect(rows).toHaveCount(2);
	await expect(rows.first()).toContainText("homelab");
	await expect(rows.last()).toContainText("trading");

	// Clicking a binding navigates to /{binding} and shows the board.
	await page.getByTestId("binding-row").filter({ hasText: "homelab" }).click();
	await expect(page).toHaveURL("/homelab");
	await expect(page.getByRole("heading", { name: "homelab" })).toBeVisible();
	await expect(page.getByTestId("column-todo")).toBeVisible();

	expectCleanConsole(problems);
});
