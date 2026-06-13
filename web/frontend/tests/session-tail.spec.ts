import {
	test,
	expect,
	appendSessionTail,
	seedSkills,
	seedRunningRunIssue,
} from "./fixtures";

test("session tail tab renders empty placeholder when no run is active", async ({
	page,
}) => {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();

	// Open the seed issue that exists from seeding
	await page.getByTestId("issue-card").first().click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Click the session tab
	await page.getByTestId("tab-session").click();

	// Should show empty placeholder since no running session
	await expect(page.getByTestId("session-tail-empty")).toBeVisible();
	await expect(page.getByTestId("session-tail-empty")).toContainText(
		"No active session",
	);
});

test("session tail tab shows live lines for a running issue", async ({ page }) => {
	seedSkills([{ name: "blueprint" }, { name: "code-review" }]);

	const title = `e2e session tail issue ${Date.now()}`;
	const { issueId } = seedRunningRunIssue("homelab", title);

	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();

	await page
		.getByTestId("issue-card")
		.filter({ hasText: title })
		.first()
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Switch to the session tab.
	await page.getByTestId("tab-session").click();

	// Should show empty placeholder until the session file receives content.
	await expect(page.getByTestId("session-tail-empty")).toBeVisible();

	appendSessionTail(issueId, {
		type: "assistant",
		content: "live tail smoke line",
	});

	await expect(page.getByTestId("session-tail-line")).toContainText(
		"live tail smoke line",
	);
});
