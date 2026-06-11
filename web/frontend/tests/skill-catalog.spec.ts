import { expect, expectCleanConsole, seedSkills, test } from "./fixtures";

test("issue flyout skill dropdown shows catalog entries", async ({
	page,
	problems,
}) => {
	seedSkills([
		{ name: "catalog-alpha", description: "Catalog alpha fixture" },
		{ name: "catalog-bravo", description: "Catalog bravo fixture" },
	]);

	await page.goto("/homelab");
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Seed todo issue for homelab" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const skill = page.getByTestId("edit-preferred_skill");
	await expect(
		skill.locator("option", { hasText: "catalog-alpha" }),
	).toBeAttached();
	await expect(
		skill.locator("option", { hasText: "catalog-bravo" }),
	).toBeAttached();

	expectCleanConsole(problems);
});
