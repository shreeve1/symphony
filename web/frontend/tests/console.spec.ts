import { test, expect, expectCleanConsole } from "./fixtures";

test("landing page loads with a clean console", async ({ page, problems }) => {
	await page.goto("/");
	// Wait until the sidebar's bindings query has resolved and rendered, so any
	// fetch/hydration error has had a chance to surface before we assert.
	await expect(page.getByTestId("binding-row").first()).toBeVisible();
	expectCleanConsole(problems);
});

test("binding page loads with a clean console", async ({ page, problems }) => {
	await page.goto("/");
	await page
		.getByTestId("binding-row")
		.filter({ hasText: /^homelab$/ })
		.click();
	await expect(page).toHaveURL("/homelab");
	await expect(page.getByTestId("column-todo")).toBeVisible();
	expectCleanConsole(problems);
});
