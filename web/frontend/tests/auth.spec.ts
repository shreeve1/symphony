import { test, expect } from "@playwright/test";

const password = "secret";

test("redirects unauthenticated visitors to login and renders board after login", async ({
	page,
}) => {
	await page.goto("/");
	await expect(page).toHaveURL(/\/login$/);
	await page.getByLabel("Password").fill(password);
	await page.getByRole("button", { name: "Log in" }).click();
	await expect(page).toHaveURL(/\/$/);
	await page.getByRole("link", { name: "trading" }).click();
	await expect(page.getByTestId("column-todo")).toBeVisible();
});
