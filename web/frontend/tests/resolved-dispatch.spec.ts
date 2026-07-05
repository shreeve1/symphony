import { expect, seedResolvedDispatchIssue, test } from "./fixtures";

// When an issue is created without an agent/model, the dispatch gate resolves
// them from the catalog/binding default and records what ran on the Run row.
// The flyout's preferred_* chips stay blank (nothing was requested), so a
// read-only "Last run used" hint surfaces the resolved values instead.
test("flyout shows resolved agent/model when preferred left unset", async ({
	page,
}) => {
	const { issueId } = seedResolvedDispatchIssue(
		"homelab",
		"Resolved dispatch hint",
		"pi",
		"deepseek-v4-pro:high",
	);

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Resolved dispatch hint",
	);
	await expect(page.getByTestId("resolved-dispatch-hint")).toHaveText(
		"Last run used: pi · deepseek-v4-pro:high",
	);
});
