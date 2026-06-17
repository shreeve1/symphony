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

async function mockBindingCapabilities(
	page: Page,
	bindingName: string,
	capabilities: { pi_mode?: "one-shot" | "rpc"; claude_persist?: boolean },
) {
	await page.route("**/api/bindings", async (route) => {
		const response = await route.fetch();
		const bindings = (await response.json()) as Record<string, unknown>[];
		await route.fulfill({
			response,
			json: bindings.map((binding) =>
				binding.name === bindingName ? { ...binding, ...capabilities } : binding,
			),
		});
	});
}

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

test("steer controls enable for Claude on claude_persist binding", async ({
	page,
	problems,
}) => {
	const title = `e2e steer claude persist ${Date.now()}`;
	seedRunningRunIssue("homelab", title, "claude");
	await mockBindingCapabilities(page, "homelab", {
		pi_mode: "one-shot",
		claude_persist: true,
	});

	await openSessionTab(page, "homelab", title);
	await expect(page.getByTestId("steer-input")).toBeEnabled();
	await expect(page.getByTestId("steer-abort")).toBeEnabled();
	await expect(page.getByTestId("steer-agent-copy")).toContainText(
		"Claude picks it up at its next turn",
	);
	await expect(page.getByTestId("steer-agent-copy")).toContainText(
		"interrupt the current turn now (Esc)",
	);

	expectCleanConsole(problems);
});

test("steer controls disable for pi one-shot on claude_persist binding", async ({
	page,
	problems,
}) => {
	const title = `e2e steer pi oneshot persist ${Date.now()}`;
	seedRunningRunIssue("homelab", title, "pi");
	await mockBindingCapabilities(page, "homelab", {
		pi_mode: "one-shot",
		claude_persist: true,
	});

	await openSessionTab(page, "homelab", title);
	await expect(page.getByTestId("steer-input")).toBeDisabled();
	await expect(page.getByTestId("steer-abort")).toBeDisabled();
	await expect(page.getByTestId("steer-disabled-hint")).toContainText(
		"not using pi RPC",
	);
	await expect(page.getByTestId("steer-agent-copy")).toBeHidden();

	expectCleanConsole(problems);
});

test("steer controls disable for Claude without claude_persist and idle issues", async ({
	page,
	problems,
}) => {
	const claudeTitle = `e2e steer claude ${Date.now()}`;
	seedRunningRunIssue("homelab", claudeTitle, "claude");
	await openSessionTab(page, "homelab", claudeTitle);
	await expect(page.getByTestId("steer-input")).toBeDisabled();
	await expect(page.getByTestId("steer-abort")).toBeDisabled();
	await expect(page.getByTestId("steer-disabled-hint")).toContainText(
		"claude_persist",
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
