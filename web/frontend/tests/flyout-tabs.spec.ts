import {
	expect,
	expectCleanConsole,
	seedIssue,
	setIssueComments,
	test,
} from "./fixtures";

test("flyout switches between Comments and Session tabs", async ({
	page,
	problems,
}) => {
	await page.goto("/dotfiles");

	// Target the seeded issue by title to stay robust against extra seed data.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Seed running issue for dotfiles" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// All seven metadata chips render (#013 added effort and base; priority and
	// max s were dropped from the flyout by operator request).
	const chips = page.getByTestId("metadata-chips").locator("> span");
	await expect(chips).toHaveCount(7);

	// Comments tab is selected by default; comments are AI-posted and render as
	// read-only formatted markdown, so assert on the rendered view text.
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"Replace with real operator thread",
	);

	// Switching to Session swaps in the steer composer + live session tail.
	await page.getByTestId("tab-session").click();
	await expect(page.getByTestId("tabpanel-session")).toBeVisible();

	// And back to Comments.
	await page.getByTestId("tab-comments").click();
	await expect(page.getByTestId("view-comments_md")).toContainText(
		"Operator comments",
	);

	const flyout = page.getByTestId("issue-flyout");
	const normalWidth = (await flyout.boundingBox())?.width ?? 0;
	const viewportWidth = page.viewportSize()?.width ?? 0;
	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);
	const maximizedWidth = (await flyout.boundingBox())?.width ?? 0;
	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeCloseTo(normalWidth, 0);
	const restoredWidth = (await flyout.boundingBox())?.width ?? 0;
	expect(restoredWidth).toBeLessThan(maximizedWidth);

	expectCleanConsole(problems);
});

test("flyout comments wrap long diagnostic blocks", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue(
		"homelab",
		"Flyout overflow diagnostic",
		"in_review",
	);
	const marker = JSON.stringify({
		consecutive_passes: 0,
		domain: "infra",
		external_id: "homelab-patrol-infra-9690678d",
		last_fail_at: "2026-06-24T15:00:34.912740+00:00",
		last_pass_at: "2026-06-23T03:00:37.152185+00:00",
		latest_status: "failed",
		severity: "medium",
	});
	setIssueComments(
		issueId,
		`### Patrol (2026-06-24T00:00:00Z)\n\n**Diagnostic:**\n\n\`\`\`\n${marker}\n\`\`\`\n`,
	);

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("flyout-issue-number")).toHaveText(
		`Issue #${issueId}`,
	);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout overflow diagnostic",
	);
	const comments = page.getByTestId("view-comments_md");
	await expect
		.poll(() =>
			comments.evaluate((el) => el.scrollWidth - el.clientWidth),
		)
		.toBeLessThanOrEqual(1);

	expectCleanConsole(problems);
});

test("flyout maximize preference follows close, reopen, issue switches, and reloads", async ({
	page,
	problems,
}) => {
	const first = seedIssue("dotfiles", "Flyout maximize memory A", "in_review");
	const second = seedIssue("dotfiles", "Flyout maximize memory B", "blocked");

	await page.goto("/dotfiles");
	await page.evaluate(() => {
		window.localStorage.removeItem("podium-flyout-maximized");
	});
	await page.goto(`/dotfiles?issue=${first.issueId}`);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory A",
	);
	const flyout = page.getByTestId("issue-flyout");
	const viewportWidth = page.viewportSize()?.width ?? 0;
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);

	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.reload();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory A",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.getByTestId("close-issue-flyout").click();
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Flyout maximize memory A" })
		.click();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory A",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.goto(`/dotfiles?issue=${second.issueId}`);
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory B",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Restore",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeGreaterThanOrEqual(viewportWidth - 1);

	await page.getByTestId("toggle-flyout-maximize").click();
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeLessThan(viewportWidth - 50);

	await page.reload();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory B",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeLessThan(viewportWidth - 50);

	await page.getByTestId("close-issue-flyout").click();
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Flyout maximize memory B" })
		.click();
	await expect(page.getByTestId("flyout-title")).toHaveText(
		"Flyout maximize memory B",
	);
	await expect(page.getByTestId("toggle-flyout-maximize")).toHaveText(
		"Maximize",
	);
	await expect
		.poll(async () => (await flyout.boundingBox())?.width ?? 0)
		.toBeLessThan(viewportWidth - 50);

	expectCleanConsole(problems);
});
