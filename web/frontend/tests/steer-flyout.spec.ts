import type { Page } from "@playwright/test";

import {
	appendSessionTail,
	expect,
	expectCleanConsole,
	finishRun,
	seedRunningRunIssue,
	test,
} from "./fixtures";

async function openSessionTab(page: Page, binding: string, title: string) {
	await page.goto(`/${binding}`);
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await page.getByTestId("tab-session").click();
	await expect(page.getByTestId("steer-composer")).toBeVisible();
}

const waitForSteer = (page: Page) =>
	page.waitForResponse(
		(res) =>
			/\/api\/issues\/\d+\/steer$/.test(res.url()) &&
			res.request().method() === "POST" &&
			res.ok(),
	);

test("session tab streams tail, sends steer, and records comments", async ({
	page,
	problems,
}) => {
	const title = `e2e steer live pi ${Date.now()}`;
	const { issueId } = seedRunningRunIssue("homelab", title);

	await openSessionTab(page, "homelab", title);

	await expect(page.getByTestId("steer-input")).toBeEnabled();
	await expect(page.getByTestId("steer-send")).toBeDisabled();
	appendSessionTail(issueId, {
		type: "assistant",
		content: "watching before steer",
	});
	await expect(page.getByTestId("session-tail-line")).toContainText(
		"watching before steer",
	);

	await page.getByTestId("steer-input").fill("steer from e2e");
	const steered = waitForSteer(page);
	await page.getByTestId("steer-send").click();
	await steered;

	await expect(page.getByTestId("steer-input")).toHaveValue("");
	await expect(page.getByTestId("steer-status")).toContainText(
		"Steer delivered",
	);
	await expect(page.getByTestId("session-tail-line").last()).toContainText(
		"steer from e2e",
	);

	await page.getByTestId("tab-comments").click();
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"Operator Steer",
	);
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"steer from e2e",
	);

	expectCleanConsole(problems);
});

test("steer controls disable for Claude and idle issues", async ({
	page,
	problems,
}) => {
	const claudeTitle = `e2e steer claude ${Date.now()}`;
	seedRunningRunIssue("homelab", claudeTitle, "claude");
	await openSessionTab(page, "homelab", claudeTitle);
	await expect(page.getByTestId("steer-input")).toBeDisabled();
	await expect(page.getByTestId("steer-abort")).toBeDisabled();
	await expect(page.getByTestId("steer-disabled-hint")).toContainText(
		"park-and-reply",
	);

	const idleTitle = `e2e steer idle ${Date.now()}`;
	const { runId } = seedRunningRunIssue("homelab", idleTitle);
	finishRun(runId, "finished before operator steer");
	await openSessionTab(page, "homelab", idleTitle);
	await expect(page.getByTestId("steer-input")).toBeDisabled();
	await expect(page.getByTestId("steer-disabled-hint")).toContainText(
		"only while a pi RPC run is active",
	);

	expectCleanConsole(problems);
});

test("abort control queues abort and shows delivered status", async ({
	page,
	problems,
}) => {
	const title = `e2e steer abort ${Date.now()}`;
	seedRunningRunIssue("homelab", title);

	await openSessionTab(page, "homelab", title);
	await expect(page.getByTestId("steer-abort")).toBeEnabled();

	const aborted = waitForSteer(page);
	await page.getByTestId("steer-abort").click();
	await aborted;

	await expect(page.getByTestId("steer-status")).toContainText(
		"Abort delivered",
	);
	await expect(page.getByTestId("session-tail-line").last()).toContainText(
		"operator_abort",
	);

	expectCleanConsole(problems);
});
