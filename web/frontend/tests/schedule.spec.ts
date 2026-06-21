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
	// Yes/No control defaults to "Yes" (next_window); nothing to type.

	const requestPromise = page.waitForRequest(
		(req) =>
			req.url().includes("/api/bindings/homelab/issues") &&
			req.method() === "POST",
	);
	await page.getByTestId("new-issue-submit").click();
	const request = await requestPromise;
	const body = JSON.parse(request.postData() ?? "{}");

	expect(body.scheduled_for).toBeUndefined();
	expect(body.schedule.reason).toBe("operator scheduled via Podium");
	expect(body.schedule.not_before).toBe("next_window");
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
	await expect(page.getByTestId("issue-schedule-mode")).toBeVisible();

	// Selecting "Yes" applies immediately (no Apply button) and the default
	// reason is used — there is nothing to type.
	const scheduleRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/schedule`) &&
			req.method() === "POST",
	);
	await page.getByTestId("issue-schedule-mode").selectOption("next_window");
	const scheduleBody = JSON.parse((await scheduleRequest).postData() ?? "{}");
	expect(scheduleBody).toEqual({
		not_before: "next_window",
		reason: "operator scheduled via Podium",
	});
	// Scheduling forces the issue into To Do (the /schedule endpoint sets it).
	await expect(page.getByTestId("edit-state")).toHaveValue("todo");

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
	// Selecting "No" unschedules immediately.
	await page.getByTestId("issue-schedule-mode").selectOption("none");
	await unscheduleRequest;
	await page.getByTestId("close-issue-flyout").click();
	await expect(card.getByTestId("scheduled-chip")).toHaveCount(0);

	expectCleanConsole(problems);
});
