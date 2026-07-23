import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

test("infra new-issue schedule defaults to no", async ({ page, problems }) => {
	const description = `e2e unscheduled create ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-schedule")).toBeVisible();
	await expect(page.getByTestId("new-issue-schedule-mode")).toHaveValue("none");

	// Description composer (no separate title field) — title is server-generated
	// from the description (#138). The flyout auto-opens on create success (F4),
	// so assert the new card AND the auto-opened flyout rather than just the
	// modal hiding.
	await page.getByTestId("new-issue-description").fill(description);
	const requestPromise = page.waitForRequest(
		(req) =>
			req.url().includes("/api/bindings/homelab/issues") &&
			req.method() === "POST",
	);
	await page.getByTestId("new-issue-submit").click();
	const request = await requestPromise;
	const body = JSON.parse(request.postData() ?? "{}");

	expect(body.scheduled_for).toBeUndefined();
	expect(body.schedule).toBeUndefined();
	await expect(page.getByTestId("new-issue-modal")).toBeHidden();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	const card = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: description });
	await expect(card).toBeVisible();
	await expect(card.getByTestId("scheduled-chip")).toHaveCount(0);

	expectCleanConsole(problems);
});

test("infra new-issue schedule uses atomic create payload when selected", async ({
	page,
	problems,
}) => {
	const description = `e2e scheduled create ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await page.getByTestId("new-issue-schedule-mode").selectOption("next_window");
	await page.getByTestId("new-issue-description").fill(description);

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
	// F4: the flyout auto-opens on create success.
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	const card = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: description });
	await expect(card).toContainText("Scheduled");

	expectCleanConsole(problems);
});

test("schedule control is hidden for coding bindings", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue(
		"dotfiles",
		`e2e coding no schedule ${Date.now()}`,
	);

	await page.goto("/dotfiles");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-schedule")).toHaveCount(0);
	await page.keyboard.press("Escape");

	await page.goto(`/dotfiles?issue=${issueId}`);
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

	// Stage "Yes" and apply via Send (staged-on-Send dispatch). The schedule
	// select only stages a draft; the POST /schedule fires when the composer
	// Send is clicked (hasStaged unlocks send-without-text).
	await page.getByTestId("issue-schedule-mode").selectOption("next_window");
	const scheduleRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/schedule`) &&
			req.method() === "POST",
	);
	await page.getByTestId("reply-send").click();
	const scheduleBody = JSON.parse((await scheduleRequest).postData() ?? "{}");
	expect(scheduleBody).toEqual({
		not_before: "next_window",
		reason: "operator scheduled via Podium",
	});
	// Scheduling forces the issue into To Do (the /schedule endpoint sets it).
	await expect(page.getByTestId("edit-state")).toHaveValue("todo");

	// After the staged dispatch applies, Send closes the flyout via onSent().
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	const card = page.getByTestId("issue-card").filter({ hasText: title });
	await expect(card.getByTestId("scheduled-chip")).toBeVisible();
	await expect(card.getByTestId("scheduled-chip")).toHaveAttribute(
		"title",
		/Scheduled:/,
	);

	await card.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	// Stage "No" and apply via Send — the staged-on-Send dispatch calls
	// DELETE /schedule instead of POST.
	await page.getByTestId("issue-schedule-mode").selectOption("none");
	const unscheduleRequest = page.waitForRequest(
		(req) =>
			req.url().endsWith(`/api/issues/${issueId}/schedule`) &&
			req.method() === "DELETE",
	);
	await page.getByTestId("reply-send").click();
	await unscheduleRequest;
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	await expect(card.getByTestId("scheduled-chip")).toHaveCount(0);

	expectCleanConsole(problems);
});

test("a held (scheduled) issue accepts an append-only comment via /comment", async ({
	page,
	problems,
}) => {
	const title = `e2e held comment ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title);

	await page.goto(`/homelab?issue=${issueId}`);
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Stage "Yes" — the composer enters comment mode because
	// composerModeFor returns `comment` whenever staged.scheduleMode != null,
	// regardless of whether the schedule has actually been applied yet.
	await page.getByTestId("issue-schedule-mode").selectOption("next_window");
	const input = page.getByTestId("reply-input");
	await expect(input).toBeEnabled();
	await input.fill("Noting context while this waits for the window.");

	// Send applies both: the staged schedule AND the append-only comment
	// (the staged dispatch path posts /comment first, then /schedule). The
	// /comment primitive is the held-issue path — /reply would re-dispatch.
	const commented = page.waitForResponse(
		(res) =>
			/\/api\/issues\/\d+\/comment$/.test(res.url()) &&
			res.request().method() === "POST" &&
			res.ok(),
	);
	await page.getByTestId("reply-send").click();
	await commented;

	// onSent closes the flyout; the issue is now held in To Do (schedule
	// applied as part of the staged dispatch) and the scheduled chip is on
	// the card.
	await expect(page.getByTestId("issue-flyout")).toBeHidden();
	const card = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: title });
	await expect(card).toBeVisible({ timeout: 4_500 });
	await expect(card.getByTestId("scheduled-chip")).toBeVisible();

	expectCleanConsole(problems);
});
