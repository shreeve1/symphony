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

test("composer restores unsent drafts per issue and across reload", async ({
	page,
	problems,
}) => {
	const suffix = Date.now();
	const titleA = `e2e reply draft A ${suffix}`;
	const titleB = `e2e reply draft B ${suffix}`;
	const { issueId: issueA } = seedIssue("homelab", titleA, "in_review");
	const { issueId: issueB } = seedIssue("homelab", titleB, "in_review");

	await page.goto(`/homelab?issue=${issueA}`);
	await expect(page.getByTestId("flyout-title")).toContainText(titleA);
	await page.getByTestId("reply-input").fill("draft for issue A");

	await page.goto(`/homelab?issue=${issueB}`);
	await expect(page.getByTestId("flyout-title")).toContainText(titleB);
	await expect(page.getByTestId("reply-input")).toHaveValue("");
	await page.getByTestId("reply-input").fill("draft for issue B");

	await page.goto(`/homelab?issue=${issueA}`);
	await expect(page.getByTestId("flyout-title")).toContainText(titleA);
	await expect(page.getByTestId("reply-input")).toHaveValue(
		"draft for issue A",
	);

	await page.reload();
	await expect(page.getByTestId("flyout-title")).toContainText(titleA);
	await expect(page.getByTestId("reply-input")).toHaveValue(
		"draft for issue A",
	);

	const replied = waitForReply(page);
	await page.getByTestId("reply-send").click();
	await replied;
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	await page.goto(`/homelab?issue=${issueA}`);
	await expect(page.getByTestId("flyout-title")).toContainText(titleA);
	await expect(page.getByTestId("reply-input")).toHaveValue("");

	expectCleanConsole(problems);
});

test("staged schedule controls still reset on issue switch", async ({
	page,
	problems,
}) => {
	const suffix = Date.now();
	const { issueId: issueA } = seedIssue(
		"homelab",
		`e2e staged schedule A ${suffix}`,
		"in_review",
	);
	const { issueId: issueB } = seedIssue(
		"homelab",
		`e2e staged schedule B ${suffix}`,
		"in_review",
	);

	await page.goto(`/homelab?issue=${issueA}`);
	await page.getByTestId("issue-schedule-mode").selectOption("next_window");
	await expect(page.getByTestId("issue-schedule-mode")).toHaveValue(
		"next_window",
	);
	await expect(page.getByText("pending")).toBeVisible();

	await page.goto(`/homelab?issue=${issueB}`);
	await expect(page.getByTestId("issue-schedule-mode")).toHaveValue("none");

	await page.goto(`/homelab?issue=${issueA}`);
	await expect(page.getByTestId("issue-schedule-mode")).toHaveValue("none");
	await expect(page.getByText("pending")).toHaveCount(0);

	expectCleanConsole(problems);
});

test("composer posts a reply, closes the flyout, and the card moves to Todo", async ({
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

	await expect(page.getByTestId("issue-flyout")).toBeHidden();

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
	seedIssue("dotfiles", title, "blocked");

	await openIssue(page, "dotfiles", title);

	const input = page.getByTestId("reply-input");
	await input.fill("Thanks — try a different approach.");

	const replied = waitForReply(page);
	await page.getByTestId("reply-send").click();
	await replied;

	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await expect(
		page
			.getByTestId("column-todo")
			.getByTestId("issue-card")
			.filter({ hasText: title }),
	).toBeVisible({ timeout: 4_500 });

	expectCleanConsole(problems);
});
