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

const waitForComment = (page: Page) =>
	page.waitForResponse(
		(res) =>
			/\/api\/issues\/\d+\/comment$/.test(res.url()) &&
			res.request().method() === "POST" &&
			res.ok(),
	);

test("Control+Enter submits from the Reply composer", async ({
	page,
	problems,
}) => {
	const title = `e2e reply shortcut ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");
	let replyCount = 0;
	await page.route(`**/api/issues/${issueId}/reply`, async (route) => {
		if (route.request().method() !== "POST") return route.fallback();
		replyCount += 1;
		await new Promise((resolve) => setTimeout(resolve, 500));
		await route.continue();
	});

	await page.goto(`/homelab?issue=${issueId}`);
	const input = page.getByTestId("reply-input");
	await expect(page.getByText("⌘/Ctrl + Enter", { exact: true })).toBeVisible();
	await expect(input).toHaveAttribute(
		"aria-keyshortcuts",
		"Meta+Enter Control+Enter",
	);
	await input.fill("Continue with the fix.");

	const replied = waitForReply(page);
	await input.press("Control+Enter");
	await expect(page.getByTestId("reply-send")).toBeDisabled();
	await input.press("Control+Enter");
	await replied;
	expect(replyCount).toBe(1);
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	expectCleanConsole(problems);
});

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

test("slash picker applies immediate controls and submits only reply prose", async ({
	page,
	problems,
}) => {
	const title = `e2e reply slash immediate ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");
	const patchBodies: Record<string, unknown>[] = [];

	await page.route("**/api/skills?binding=homelab", (route) =>
		route.fulfill({
			contentType: "application/json",
			body: JSON.stringify([{ name: "alpha" }]),
		}),
	);
	await page.route("**/api/bindings/homelab/options", async (route) => {
		const response = await route.fetch();
		await route.fulfill({
			response,
			json: {
				agents: ["pi", "claude"],
				models: [
					{ id: "pi-a", agent: "pi", efforts: ["low"] },
					{ id: "claude-a", agent: "claude", efforts: ["low"] },
				],
				branches: ["main", "release"],
			},
		});
	});
	await page.route("**/api/issues/*", async (route) => {
		if (route.request().method() === "PATCH") {
			patchBodies.push(route.request().postDataJSON());
		}
		await route.fallback();
	});
	await page.goto(`/homelab?issue=${issueId}`);
	const input = page.getByTestId("reply-input");
	const prose = "Keep /srv/app and https://example.test/a prefix/hold. ";
	await input.fill(prose);

	const select = async (field: string, title: string, value: string) => {
		await input.pressSequentially(`/${field}`);
		await input.press("Tab");
		await expect(
			page.getByRole("listbox", { name: `${title} values` }),
		).toBeVisible();
		await input.pressSequentially(value);
		await input.press("Tab");
		await expect(input).toHaveValue(prose);
	};

	await select("skill", "Skill", "alpha");
	await select("agent", "Agent", "claude");
	await input.pressSequentially("/model");
	await input.press("Tab");
	const modelValues = page.getByRole("listbox", { name: "Model values" });
	await expect(modelValues.getByRole("option", { name: "claude-a" })).toBeVisible();
	await expect(modelValues.getByRole("option", { name: "pi-a" })).toHaveCount(0);
	await input.pressSequentially("claude-a");
	await input.press("Tab");
	await expect(input).toHaveValue(prose);
	await input.pressSequentially("/effort");
	await input.press("Tab");
	await expect(
		page
			.getByRole("listbox", { name: "Effort values" })
			.getByRole("option", { name: "xhigh" }),
	).toBeVisible();
	await input.pressSequentially("xhigh");
	await input.press("Tab");
	await select("hold", "Hold", "active");
	await select("base", "Base", "release");
	await select("base", "Base", "hotfix");
	await select("hold", "Hold", "off");

	await expect(page.getByTestId("edit-preferred_skill")).toHaveValue("alpha");
	await expect(page.getByTestId("edit-preferred_agent")).toHaveValue("claude");
	await expect(page.getByTestId("edit-preferred_model")).toHaveValue("claude-a");
	await expect(page.getByTestId("edit-reasoning_effort")).toHaveValue("xhigh");
	await expect(page.getByTestId("edit-base_branch")).toHaveValue("hotfix");
	await expect(page.getByTestId("edit-hold")).toHaveAttribute(
		"aria-pressed",
		"false",
	);
	await expect.poll(() => patchBodies.length).toBe(8);
	expect(patchBodies).toEqual([
		{ preferred_skill: "alpha" },
		{ preferred_agent: "claude" },
		{ preferred_model: "claude-a" },
		{ reasoning_effort: "xhigh" },
		{ hold: true },
		{ base_branch: "release" },
		{ base_branch: "hotfix" },
		{ hold: false },
	]);

	await input.pressSequentially("Continue.");
	const replyRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/reply`) &&
			req.method() === "POST",
	);
	await page.getByTestId("reply-send").click();
	expect((await replyRequest).postDataJSON()).toEqual({
		body: `${prose}Continue.`,
	});
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	expectCleanConsole(problems);
});

test("slash picker stages approval and schedule until Send and respects binding visibility", async ({
	page,
	problems,
}) => {
	const title = `e2e reply slash staged ${Date.now()}`;
	const codingTitle = `e2e reply slash coding ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");
	const { issueId: codingIssueId } = seedIssue(
		"dotfiles",
		codingTitle,
		"in_review",
	);
	let dispatchRequestCount = 0;

	await page.route("**/api/bindings", async (route) => {
		const response = await route.fetch();
		const bindings = (await response.json()) as Record<string, unknown>[];
		await route.fulfill({
			response,
			json: bindings.map((binding) =>
				binding.name === "homelab"
					? { ...binding, approval_enabled: true }
					: binding,
			),
		});
	});
	page.on("request", (request) => {
		if (
			(request.method() === "PATCH" &&
				request.url().endsWith(`/api/issues/${issueId}`)) ||
			request.url().endsWith(`/api/issues/${issueId}/schedule`)
		) {
			dispatchRequestCount += 1;
		}
	});
	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("edit-approval_required")).toBeVisible();
	const input = page.getByTestId("reply-input");
	await input.fill("Apply these controls. ");

	for (const [field, title, value] of [
		["approval", "Approval", "active"],
		["approved", "Approved", "active"],
		["schedule", "Schedule", "yes"],
	] as const) {
		await input.pressSequentially(`/${field}`);
		await input.press("Tab");
		await expect(
			page.getByRole("listbox", { name: `${title} values` }),
		).toBeVisible();
		await input.pressSequentially(value);
		await input.press("Tab");
	}

	await expect(page.getByTestId("edit-approval_required")).toHaveText("active");
	await expect(page.getByTestId("edit-approved")).toHaveText("active");
	await expect(page.getByTestId("issue-schedule-mode")).toHaveValue(
		"next_window",
	);
	expect(dispatchRequestCount).toBe(0);

	const approvalRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}`) && req.method() === "PATCH",
	);
	const commentRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/comment`) &&
			req.method() === "POST",
	);
	const scheduleRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/schedule`) &&
			req.method() === "POST",
	);
	await page.getByTestId("reply-send").click();
	expect((await approvalRequest).postDataJSON()).toEqual({
		approval_required: true,
		approved: true,
	});
	expect((await commentRequest).postDataJSON().body.trim()).toBe(
		"Apply these controls.",
	);
	expect((await scheduleRequest).postDataJSON()).toMatchObject({
		not_before: "next_window",
	});
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	await page.goto(`/dotfiles?issue=${codingIssueId}`);
	await page.getByTestId("reply-input").fill("/");
	await expect(page.getByRole("option", { name: "Approval" })).toHaveCount(0);
	await expect(page.getByRole("option", { name: "Approved" })).toHaveCount(0);
	await expect(page.getByRole("option", { name: "Schedule" })).toHaveCount(0);
	await page.unrouteAll({ behavior: "ignoreErrors" });

	expectCleanConsole(problems);
});

test("composer posts a reply, closes the flyout, and the card moves to Todo", async ({
	page,
	problems,
}) => {
	const title = `e2e reply in_review issue ${Date.now()}`;
	seedIssue("homelab", title, "in_review");

	await openIssue(page, "homelab", title);

	// Comments tab is selected by default; the composer follows the thread.
	const input = page.getByTestId("reply-input");
	await expect(input).toBeVisible();
	await expect(page.getByTestId("reply-send")).toBeVisible();
	expect(
		await page
			.locator('[data-testid="view-comments_md"], [data-testid="reply-input"]')
			.evaluateAll((elements) =>
				elements.map((element) => element.getAttribute("data-testid")),
			),
	).toEqual(["view-comments_md", "reply-input"]);

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

test("failed Reply keeps the flyout and draft open with an error", async ({
	page,
	problems,
}) => {
	const title = `e2e reply failure ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");

	await page.route(`**/api/issues/${issueId}/reply`, (route) =>
		route.fulfill({
			status: 409,
			contentType: "application/json",
			body: JSON.stringify({ detail: "stubbed reply conflict" }),
		}),
	);
	await page.goto(`/homelab?issue=${issueId}`);
	const input = page.getByTestId("reply-input");
	await input.fill("Keep this draft after failure.");
	const rejected = page.waitForResponse(
		(res) => res.url().endsWith(`/api/issues/${issueId}/reply`),
	);
	await page.getByTestId("reply-send").click();
	await rejected;

	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("reply-error")).toBeVisible();
	await expect(input).toHaveValue("Keep this draft after failure.");

	expectCleanConsole(problems, { ignore: [/409/] });
});

test("running non-steerable issue routes the composer to comment-mode with a hint", async ({
	page,
	problems,
}) => {
	const title = `e2e reply running non-steerable ${Date.now()}`;
	seedRunningRunIssue("homelab", title, "pi");
	// pi + one-shot binding → composer auto-routes to comment-mode (live,
	// non-steerable); §7 case "Live, non-steerable → Comment · agent sees it
	// next park".
	await page.route("**/api/bindings", async (route) => {
		const response = await route.fetch();
		const bindings = (await response.json()) as Record<string, unknown>[];
		await route.fulfill({
			response,
			json: bindings.map((binding) =>
				binding.name === "homelab"
					? { ...binding, pi_mode: "one-shot" }
					: binding,
			),
		});
	});

	await openIssue(page, "homelab", title);

	await expect(page.getByTestId("reply-composer")).toBeVisible();
	await expect(page.getByTestId("composer-mode-pill")).toHaveText(
		"Comment · agent sees it next park",
	);
	await expect(page.getByTestId("reply-input")).toBeEnabled();
	await expect(page.getByTestId("reply-send")).toBeDisabled();
	await expect(page.getByTestId("reply-disabled-hint")).toContainText(
		"Agent is running",
	);
	await page.getByTestId("reply-input").fill("Save this for the next park.");
	const commented = waitForComment(page);
	await page.getByTestId("reply-send").click();
	await commented;
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	await page.unrouteAll({ behavior: "ignoreErrors" });
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

test("mode pill is always visible and names mode + consequence", async ({
	page,
	problems,
}) => {
	const title = `e2e reply mode pill in_review ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("reply-composer")).toBeVisible();
	await expect(page.getByTestId("composer-mode-pill")).toHaveText(
		"Reply · re-dispatches",
	);

	expectCleanConsole(problems);
});

test("scheduled-hold todo routes the composer to Comment · note pill", async ({
	page,
	problems,
}) => {
	const title = `e2e reply scheduled ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "todo");
	// Force scheduled_for on this todo row so the §7 scheduled-hold case
	// (todo + scheduled_for → comment-note) applies.
	await page.route(`**/api/issues/${issueId}`, async (route) => {
		const request = route.request();
		if (request.method() !== "GET") return route.fallback();
		const response = await route.fetch();
		const detail = (await response.json()) as Record<string, unknown>;
		await route.fulfill({
			response,
			json: { ...detail, scheduled_for: "2099-01-01T00:00:00Z" },
		});
	});

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("reply-composer")).toBeVisible();
	await expect(page.getByTestId("composer-mode-pill")).toHaveText(
		"Comment · note",
	);
	await page.getByTestId("reply-input").fill("Hold note.");
	const commented = waitForComment(page);
	await page.getByTestId("reply-send").click();
	await commented;

	await page.unrouteAll({ behavior: "ignoreErrors" });
	expectCleanConsole(problems);
});

test("your-turn affordance renders for state=in_review", async ({
	page,
	problems,
}) => {
	const title = `e2e reply your turn ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("state-chip-sublabel")).toHaveText("your turn");

	expectCleanConsole(problems);
});

test("freshly created todo routes to Comment · seed and focuses it", async ({
	page,
	problems,
}) => {
	const description = `e2e reply fresh todo ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-description").fill(description);
	await page.getByTestId("new-issue-submit").click();

	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("composer-mode-pill")).toHaveText(
		"Comment · seed",
	);
	await expect(page.getByTestId("reply-input")).toBeFocused();

	await page.getByTestId("reply-input").fill("Initial context.");
	const commented = waitForComment(page);
	await page.getByTestId("reply-send").click();
	await commented;

	expectCleanConsole(problems);
});
