import type { Page } from "@playwright/test";

import {
	authenticate,
	expect,
	expectCleanConsole,
	finishRun,
	finishRunWithIssueComment,
	seedIssue,
	seedRunningRunIssue,
	test,
	updateIssueState,
} from "./fixtures";
import {
	issueDetailRefetchIntervalMs,
	issueListRefetchIntervalMs,
	runDetailRefetchIntervalMs,
	runListRefetchIntervalMs,
} from "../lib/polling";
import { formatRunDuration } from "../lib/run-duration";

const LIVE_SYNC_CARD = "Seed todo issue for homelab";

async function openIssue(page: Page, title: string) {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
}

const waitForPatch = (page: Page) =>
	page.waitForResponse(
		(res) =>
			res.url().includes("/api/issues/") &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

test("running duration helper formats live and terminal states", async () => {
	const started = "2026-06-12T00:00:00Z";
	expect(
		formatRunDuration(
			{ state: "running", started_at: started, ended_at: null },
			Date.parse("2026-06-12T00:04:12Z"),
		),
	).toBe("running 4m12s");
	expect(
		formatRunDuration({
			state: "succeeded",
			started_at: started,
			ended_at: "2026-06-12T00:00:09Z",
		}),
	).toBe("9s");
	expect(
		formatRunDuration({
			state: "succeeded",
			started_at: started,
			ended_at: null,
		}),
	).toBe("—");
});

test("polling interval helpers gate active and idle states", async () => {
	expect(issueListRefetchIntervalMs([])).toBe(10_000);
	expect(
		issueListRefetchIntervalMs([
			{
				id: 1,
				binding_name: "homelab",
				binding_type: "coding",
				title: "running issue",
				description: null,
				state: "running",
				priority: null,
				preferred_agent: null,
				preferred_model: null,
				preferred_skill: null,
				reasoning_effort: null,
				worktree_active: false,
				approval_required: false,
				approved: false,
				scheduled_for: null,
				worktree_path: "worktrees/homelab/1",
				worktree_branch: "podium/homelab/1",
				base_branch: null,
				created_at: null,
				updated_at: null,
				latest_run_id: null,
				latest_verdict: null,
				latest_run_state: null,
				last_event_at: null,
			},
		]),
	).toBe(3_000);
	expect(
		issueListRefetchIntervalMs([
			{
				id: 2,
				binding_name: "homelab",
				binding_type: "coding",
				title: "queued run",
				description: null,
				state: "todo",
				priority: null,
				preferred_agent: null,
				preferred_model: null,
				preferred_skill: null,
				reasoning_effort: null,
				worktree_active: false,
				approval_required: false,
				approved: false,
				scheduled_for: null,
				worktree_path: "worktrees/homelab/2",
				worktree_branch: "podium/homelab/2",
				base_branch: null,
				created_at: null,
				updated_at: null,
				latest_run_id: 1,
				latest_verdict: null,
				latest_run_state: "queued",
				last_event_at: null,
			},
		]),
	).toBe(3_000);
	expect(
		issueDetailRefetchIntervalMs({ state: "todo", latest_run_state: null }),
	).toBe(3_000);
	expect(
		issueDetailRefetchIntervalMs({
			state: "in_review",
			latest_run_state: "running",
		}),
	).toBe(3_000);
	expect(
		issueDetailRefetchIntervalMs({
			state: "in_review",
			latest_run_state: "succeeded",
		}),
	).toBe(false);
	expect(runListRefetchIntervalMs([{ state: "queued" }])).toBe(3_000);
	expect(runListRefetchIntervalMs([{ state: "succeeded" }])).toBe(false);
	expect(runDetailRefetchIntervalMs({ state: "running" })).toBe(3_000);
	expect(runDetailRefetchIntervalMs({ state: "succeeded" })).toBe(false);
});

test("board polling picks up direct database issue state changes", async ({
	page,
	problems,
}) => {
	const title = `e2e polled board issue ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title);

	await page.goto("/homelab");
	const todoCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: title });
	await expect(todoCard).toBeVisible();

	updateIssueState(issueId, "blocked");
	await expect(
		page
			.getByTestId("column-blocked")
			.getByTestId("issue-card")
			.filter({ hasText: title }),
	).toBeVisible({ timeout: 11_000 });

	expectCleanConsole(problems);
});

test("run detail polling picks up terminal run metadata and log", async ({
	page,
	problems,
}) => {
	const title = `e2e polled run issue ${Date.now()}`;
	const { runId } = seedRunningRunIssue("homelab", title);

	await page.goto("/homelab");
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("run-row").first()).toContainText(
		/running \d+s/,
	);
	await page.getByTestId("run-row").first().click();
	await expect(page.getByTestId("run-detail-flyout")).toBeVisible();
	await expect(page.getByTestId("run-field-duration")).toContainText(
		/running \d+s/,
	);
	const firstDuration = await page
		.getByTestId("run-field-duration")
		.textContent();
	await expect
		.poll(async () => page.getByTestId("run-field-duration").textContent(), {
			timeout: 2_500,
		})
		.not.toBe(firstDuration);

	finishRun(runId, "polling complete\n");
	await expect(page.getByTestId("run-field-ended")).not.toContainText("—", {
		timeout: 4_500,
	});
	await expect(page.getByTestId("run-field-duration")).not.toContainText(
		"running",
	);
	await expect(page.getByTestId("run-field-duration")).toContainText(/\d+s/);
	await expect(page.getByTestId("run-log-pane")).toContainText(
		"polling complete",
		{ timeout: 4_500 },
	);

	expectCleanConsole(problems, {
		ignore: [
			/Failed to load resource: the server responded with a status of 404/,
			/httperror: 404 GET .*\/api\/runs\/\d+\/log/,
		],
	});
});

test("open flyout polls scheduler-written completion comments", async ({
	page,
	problems,
}) => {
	const title = `e2e flyout completion poll ${Date.now()}`;
	const { runId } = seedRunningRunIssue("homelab", title);
	const aiSummary = "AI completion from direct scheduler write";

	await openIssue(page, title);
	await expect(page.getByTestId("view-comments_md")).not.toContainText(
		aiSummary,
	);

	finishRunWithIssueComment(runId, `### Symphony AI Summary\n\n${aiSummary}`);

	await expect(page.getByTestId("view-comments_md")).toContainText(aiSummary, {
		timeout: 7_000,
	});

	expectCleanConsole(problems);
});

test("live issue updates sync between browser contexts", async ({
	browser,
	page,
	problems,
}) => {
	const other = await browser.newPage();
	await authenticate(other);
	const otherProblems: string[] = [];
	other.on("console", (msg) => {
		if (msg.type() === "error")
			otherProblems.push(`console.error: ${msg.text()}`);
	});
	other.on("pageerror", (err) =>
		otherProblems.push(`pageerror: ${err.message}`),
	);
	other.on("requestfailed", (req) => {
		const failure = req.failure()?.errorText ?? "unknown";
		otherProblems.push(
			`requestfailed: ${req.method()} ${req.url()} (${failure})`,
		);
	});
	other.on("response", (res) => {
		if (res.status() >= 400) {
			otherProblems.push(
				`httperror: ${res.status()} ${res.request().method()} ${res.url()}`,
			);
		}
	});

	try {
		await openIssue(page, LIVE_SYNC_CARD);
		await openIssue(other, LIVE_SYNC_CARD);

		const state = page.getByTestId("edit-state");
		const nextState =
			(await state.inputValue()) === "blocked" ? "todo" : "blocked";
		const patched = waitForPatch(page);
		await state.selectOption(nextState);
		await patched;

		await expect(other.getByTestId("edit-state")).toHaveValue(nextState, {
			timeout: 3_000,
		});
	} finally {
		await other.close();
	}

	expectCleanConsole(problems);
	expect(otherProblems).toEqual([]);
});

test("disconnected pill renders while websocket reconnects", async ({
	context,
	page,
	problems,
}) => {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();

	await context.setOffline(true);
	await expect(page.getByTestId("connection-pill")).toContainText(
		"Disconnected — retrying",
	);

	await context.setOffline(false);
	await expect(page.getByTestId("connection-pill")).toBeHidden({
		timeout: 5_000,
	});

	expectCleanConsole(problems, { ignore: [/ERR_INTERNET_DISCONNECTED/] });
});
