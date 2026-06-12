import type { Page } from "@playwright/test";

import {
	expect,
	expectCleanConsole,
	seedIssue,
	seedRunningRunIssue,
	test,
} from "./fixtures";

// Real backend e2e: seed an issue directly in the throwaway Podium DB, open its
// flyout (comments tab is selected by default), and drive the reply composer
// against the live POST /api/issues/{id}/reply endpoint. The card move to Todo
// is asserted via the live board update (WS issue.updated + query invalidation),
// matching live-sync.spec.ts.

async function openIssue(page: Page, binding: string, title: string) {
	await page.goto(`/${binding}`);
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
}

const waitForReply = (page: Page) =>
	page.waitForResponse(
		(res) =>
			/\/api\/issues\/\d+\/reply$/.test(res.url()) &&
			res.request().method() === "POST" &&
			res.ok(),
	);

test("composer posts a reply, clears the input, and the card moves to Todo", async ({
	page,
	problems,
}) => {
	const title = `e2e reply in_review issue ${Date.now()}`;
	seedIssue("homelab", title, "in_review");

	await openIssue(page, "homelab", title);

	// Comments tab is selected by default; the composer renders below the editor.
	const input = page.getByTestId("reply-input");
	await expect(input).toBeVisible();
	await expect(page.getByTestId("reply-send")).toBeVisible();

	await input.fill("Please continue with the next step.");

	const replied = waitForReply(page);
	await page.getByTestId("reply-send").click();
	await replied;

	// Draft clears on success.
	await expect(input).toHaveValue("");

	// Live board update flips the card into the Todo column.
	await expect(
		page
			.getByTestId("column-todo")
			.getByTestId("issue-card")
			.filter({ hasText: title }),
	).toBeVisible({ timeout: 4_500 });

	expectCleanConsole(problems);
});

test("composer send is disabled with a hint while the issue is running", async ({
	page,
	problems,
}) => {
	const title = `e2e reply running issue ${Date.now()}`;
	seedRunningRunIssue("homelab", title);

	await openIssue(page, "homelab", title);

	await expect(page.getByTestId("reply-send")).toBeDisabled();
	await expect(page.getByTestId("reply-input")).toBeDisabled();
	await expect(page.getByTestId("reply-disabled-hint")).toContainText(
		"Agent is running",
	);

	expectCleanConsole(problems);
});

test("no console errors during the reply flow", async ({ page, problems }) => {
	const title = `e2e reply console issue ${Date.now()}`;
	seedIssue("trading", title, "blocked");

	await openIssue(page, "trading", title);

	const input = page.getByTestId("reply-input");
	await input.fill("Thanks — try a different approach.");

	const replied = waitForReply(page);
	await page.getByTestId("reply-send").click();
	await replied;

	await expect(input).toHaveValue("");
	await expect(
		page
			.getByTestId("column-todo")
			.getByTestId("issue-card")
			.filter({ hasText: title }),
	).toBeVisible({ timeout: 4_500 });

	expectCleanConsole(problems);
});
