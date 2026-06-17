import type { Page } from "@playwright/test";

import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

const waitForIssuePatch = (issueId: number, page: Page) =>
	page.waitForResponse(
		(res) =>
			res.url().includes(`/api/issues/${issueId}`) &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

async function openSeededIssue(page: Page, title: string) {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
}

test("state changes to done and archived close the flyout", async ({
	page,
	problems,
}) => {
	for (const state of ["done", "archived"] as const) {
		const title = `e2e flyout auto-close ${state} ${Date.now()}`;
		const { issueId } = seedIssue("homelab", title, "in_review");
		await openSeededIssue(page, title);

		const patched = waitForIssuePatch(issueId, page);
		await page.getByTestId("edit-state").selectOption(state);
		await patched;

		await expect(page.getByTestId("issue-flyout")).toBeHidden();
	}

	expectCleanConsole(problems);
});

test("ordinary metadata edits keep the flyout open", async ({
	page,
	problems,
}) => {
	const title = `e2e flyout stays open ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");
	await openSeededIssue(page, title);

	const patched = waitForIssuePatch(issueId, page);
	await page.getByTestId("edit-reasoning_effort").selectOption("medium");
	await patched;

	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	expectCleanConsole(problems);
});
