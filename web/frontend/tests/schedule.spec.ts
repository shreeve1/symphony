import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

test("infra new-issue schedule uses atomic create payload", async ({
	page,
	problems,
}) => {
	const title = `e2e scheduled create ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-schedule")).toBeVisible();
	await expect(page.getByTestId("new-issue-schedule-mode")).toHaveValue(
		"next_window",
	);

	await page.getByTestId("new-issue-title").fill(title);
	await page.getByTestId("new-issue-schedule-mode").selectOption("custom");
	await page.getByTestId("new-issue-schedule-custom").fill("2031-02-03T04:05");
	await page.getByTestId("new-issue-schedule-reason").fill("e2e custom window");

	const requestPromise = page.waitForRequest(
		(req) =>
			req.url().includes("/api/bindings/homelab/issues") &&
			req.method() === "POST",
	);
	await page.getByTestId("new-issue-submit").click();
	const request = await requestPromise;
	const body = JSON.parse(request.postData() ?? "{}");

	expect(body.scheduled_for).toBeUndefined();
	expect(body.schedule.reason).toBe("e2e custom window");
	expect(body.schedule.not_before).toMatch(
		/^2031-02-03T04:05:00[+-]\d{2}:\d{2}$/,
	);
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();
	await expect(
		page.getByTestId("issue-card").filter({ hasText: title }),
	).toContainText("Scheduled");

	expectCleanConsole(problems);
});

test("schedule control is hidden for coding bindings", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue(
		"trading",
		`e2e coding no schedule ${Date.now()}`,
	);

	await page.goto("/trading");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-schedule")).toHaveCount(0);
	await page.keyboard.press("Escape");

	await page.goto(`/trading?issue=${issueId}`);
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("issue-schedule")).toHaveCount(0);

	expectCleanConsole(problems);
});

test("flyout schedules, unschedules, and the board card shows held todos", async ({
	page,
	problems,
}) => {
	const title = `e2e flyout schedule ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title);

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("issue-schedule")).toBeVisible();
	await page.getByTestId("issue-schedule-mode").selectOption("next_window");
	await page.getByTestId("issue-schedule-reason").fill("flyout e2e schedule");

	const scheduleRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/schedule`) &&
			req.method() === "POST",
	);
	await page.getByTestId("issue-schedule-apply").click();
	const scheduleBody = JSON.parse((await scheduleRequest).postData() ?? "{}");
	expect(scheduleBody).toEqual({
		not_before: "next_window",
		reason: "flyout e2e schedule",
	});
	await expect(page.getByTestId("issue-schedule-current")).toBeVisible();

	await page.getByTestId("close-issue-flyout").click();
	const card = page.getByTestId("issue-card").filter({ hasText: title });
	await expect(card.getByTestId("scheduled-chip")).toBeVisible();
	await expect(card.getByTestId("scheduled-chip")).toHaveAttribute(
		"title",
		/Scheduled:/,
	);

	await card.click();
	const unscheduleRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/schedule`) &&
			req.method() === "DELETE",
	);
	await page.getByTestId("issue-schedule-clear").click();
	await unscheduleRequest;
	await page.getByTestId("close-issue-flyout").click();
	await expect(card.getByTestId("scheduled-chip")).toHaveCount(0);

	expectCleanConsole(problems);
});
