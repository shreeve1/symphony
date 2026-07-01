import { expect, expectCleanConsole, test } from "./fixtures";

test("run detail opens from issue flyout and reloads its log", async ({
	page,
	problems,
}) => {
	await page.goto("/dotfiles");

	// Target the seeded running issue by title so extra seed data doesn't shift ordering.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Seed running issue for dotfiles" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	await page.getByTestId("run-row").first().click();
	await expect(page.getByTestId("run-detail-flyout")).toBeVisible();
	await expect(page.getByTestId("run-metadata-grid")).toBeVisible();
	await expect(page.getByTestId("run-log-pane")).toContainText(
		"No log on disk for this run.",
	);
	await expect(page.getByTestId("run-cost")).toHaveCount(0);

	const logResponse = page.waitForResponse((response) =>
		/api\/runs\/\d+\/log$/.test(response.url()),
	);
	await page.getByTestId("reload-run-log").click();
	await logResponse;

	expectCleanConsole(problems, {
		ignore: [
			/Failed to load resource: the server responded with a status of 404/,
			/httperror: 404 GET .*\/api\/runs\/\d+\/log/,
		],
	});
});
