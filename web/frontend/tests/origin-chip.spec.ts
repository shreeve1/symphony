import {
	expect,
	expectCleanConsole,
	seedIssue,
	seedIssueWithOrigin,
	test,
} from "./fixtures";

// Issue #461: surface issue.origin in the UI so automation-spawned issues
// are visually distinct from operator and patrol rows. Operator is the default
// and renders no chip; we only test the two non-default origins.

test.describe("Origin chip (#461)", () => {
	test("operator cards hide the origin chip", async ({ page, problems }) => {
		const title = `e2e origin operator ${Date.now()}`;
		seedIssue("homelab", title, "todo");

		await page.goto("/homelab");
		const card = page.getByTestId("issue-card").filter({ hasText: title });
		await expect(card).toBeVisible();
		await expect(card.getByTestId("origin-chip")).toHaveCount(0);

		expectCleanConsole(problems);
	});

	test("automation cards render the origin chip", async ({
		page,
		problems,
	}) => {
		const title = `e2e origin automation ${Date.now()}`;
		seedIssueWithOrigin("homelab", title, "automation", "todo");

		await page.goto("/homelab");
		const card = page.getByTestId("issue-card").filter({ hasText: title });
		await expect(card).toBeVisible();
		await expect(card.getByTestId("origin-chip")).toHaveText(/automation/i);

		expectCleanConsole(problems);
	});

	test("patrol cards render the origin chip", async ({ page, problems }) => {
		const title = `e2e origin patrol ${Date.now()}`;
		seedIssueWithOrigin("homelab", title, "patrol", "todo");

		await page.goto("/homelab");
		const card = page.getByTestId("issue-card").filter({ hasText: title });
		await expect(card).toBeVisible();
		await expect(card.getByTestId("origin-chip")).toHaveText(/patrol/i);

		expectCleanConsole(problems);
	});

	test("flyout shows the automation origin chip on the metadata strip", async ({
		page,
		problems,
	}) => {
		const title = `e2e origin flyout ${Date.now()}`;
		seedIssueWithOrigin("homelab", title, "automation", "todo");

		await page.goto("/homelab");
		await page.getByTestId("issue-card").filter({ hasText: title }).click();
		await expect(page.getByTestId("issue-flyout")).toBeVisible();
		await expect(
			page.getByTestId("metadata-chips").getByTestId("origin-chip"),
		).toHaveText(/automation/i);

		expectCleanConsole(problems);
	});
});
