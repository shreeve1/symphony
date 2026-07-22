import {
	expect,
	expectCleanConsole,
	seedIssue,
	seedRunningRunIssue,
	setIssueComments,
	test,
} from "./fixtures";

// F1 (§2.1 / §2.2): the comments tab splits on the header grammar into
// per-role bubbles and renders un-headered prose as a single collapsed
// legacy bucket. This spec covers both shapes so a future regression in
// either path lands here.
test("new-format header comments split into per-role bubbles in order", async ({
	page,
	problems,
}) => {
	const title = `comments-bubble-split ${Date.now()}`;
	const { issueId } = seedIssue("dotfiles", title, "in_review");
	const entries = [
		"### agent · 2026-06-23T11:00:00Z",
		"AGENT_FIRST_UNIQUE\n\nFirst agent turn.",
		"### operator · 2026-06-23T12:00:00Z",
		"OPERATOR_FIRST_UNIQUE\n\nOperator follow-up.",
		"### patrol · 2026-06-23T12:30:00Z",
		"PATROL_FIRST_UNIQUE\n\nPatrol note — pass 1/3.",
		"### agent · 2026-06-23T13:00:00Z",
		"AGENT_SECOND_UNIQUE\n\nSecond agent turn.",
		"### operator · 2026-06-23T14:00:00Z",
		"OPERATOR_LATEST_UNIQUE\n\nFinal operator note.",
	];
	setIssueComments(issueId, entries.join("\n\n"));

	await page.goto("/dotfiles");
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const comments = page.getByTestId("view-comments_md");
	// One bubble per headered entry, in chronological order.
	await expect(comments.getByTestId("bubble-agent")).toHaveCount(2);
	await expect(comments.getByTestId("bubble-operator")).toHaveCount(2);
	await expect(comments.getByTestId("bubble-patrol")).toHaveCount(1);

	const markers = [
		"AGENT_FIRST_UNIQUE",
		"OPERATOR_FIRST_UNIQUE",
		"PATROL_FIRST_UNIQUE",
		"AGENT_SECOND_UNIQUE",
		"OPERATOR_LATEST_UNIQUE",
	];
	const rendered = (await comments.textContent()) ?? "";
	const positions = markers.map((marker) => rendered.indexOf(marker));
	expect(positions).toEqual([...positions].sort((a, b) => a - b));

	expectCleanConsole(problems);
});

test("legacy un-headered prose collapses into a single legacy bucket", async ({
	page,
	problems,
}) => {
	const title = `comments-legacy-bucket ${Date.now()}`;
	const { issueId } = seedIssue("dotfiles", title, "in_review");
	// None of these lines match the §2.1 header regex — every line falls into
	// the un-headered prose bucket that becomes a single collapsed bucket.
	const entries = [
		"**Symphony completed:**\n\nFIRST_COMPLETION_UNIQUE work done.",
		"### Operator Reply (2026-06-23T12:00:00+00:00)\n\nFIRST_OP_REPLY_UNIQUE do more.",
		"### Patrol (2026-06-23T12:30:00+00:00)\n\nPATROL_NOTE_UNIQUE pass — 1/3.",
		"**Symphony completed:**\n\nSECOND_COMPLETION_UNIQUE more work done.",
		"### Operator Reply (2026-06-23T13:00:00+00:00)\n\nLATEST_OP_REPLY_UNIQUE final note.",
	];
	setIssueComments(issueId, entries.join("\n\n"));

	await page.goto("/dotfiles");
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const comments = page.getByTestId("view-comments_md");
	// All five old-format entries fold into exactly one legacy bucket.
	await expect(comments.getByTestId("legacy-bucket")).toHaveCount(1);
	// No new-format bubbles were synthesized.
	await expect(comments.locator('[data-testid^="bubble-"]')).toHaveCount(0);

	// The legacy bucket is collapsed by default; expanding it surfaces the
	// prose body in original source order.
	const bucket = comments.getByTestId("legacy-bucket");
	await expect(bucket.getByTestId("legacy-toggle")).toHaveAttribute(
		"aria-expanded",
		"false",
	);
	await bucket.getByTestId("legacy-toggle").click();
	await expect(bucket.getByTestId("legacy-toggle")).toHaveAttribute(
		"aria-expanded",
		"true",
	);

	const rendered = (await comments.textContent()) ?? "";
	const markers = [
		"FIRST_COMPLETION_UNIQUE",
		"FIRST_OP_REPLY_UNIQUE",
		"PATROL_NOTE_UNIQUE",
		"SECOND_COMPLETION_UNIQUE",
		"LATEST_OP_REPLY_UNIQUE",
	];
	for (const marker of markers) {
		expect(rendered).toContain(marker);
	}
	const positions = markers.map((marker) => rendered.indexOf(marker));
	expect(positions).toEqual([...positions].sort((a, b) => a - b));

	expectCleanConsole(problems);
});

test("run bubbles interleave with comment bubbles by timestamp", async ({
	page,
	problems,
}) => {
	const title = `comments-run-interleave ${Date.now()}`;
	const { issueId } = seedRunningRunIssue("dotfiles", title);
	// The seeded run is stamped with `started_at = now`. We pick an absolute
	// pre-run timestamp earlier than any reasonable test run and an
	// absolute post-run timestamp later than now so the interleave rule is
	// unambiguous regardless of clock skew.
	const beforeTs = "2020-01-01T00:00:00Z";
	const afterTs = "2099-12-31T23:59:59Z";
	const entries = [
		`### agent · ${beforeTs}`,
		"AGENT_BEFORE_RUN_UNIQUE\n\nBefore any run.",
		`### agent · ${afterTs}`,
		"AGENT_AFTER_RUN_UNIQUE\n\nAfter the run started.",
	];
	setIssueComments(issueId, entries.join("\n\n"));

	await page.goto("/dotfiles");
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const comments = page.getByTestId("view-comments_md");
	// Two comment bubbles + at least one run-start bubble from the seeded run.
	await expect(comments.getByTestId("bubble-agent")).toHaveCount(2);
	await expect(comments.getByTestId("run-start-bubble").first()).toBeVisible();

	const rendered = (await comments.textContent()) ?? "";
	// The pre-run agent bubble must appear before the run-start marker and
	// the run-start marker must appear before the post-run agent bubble.
	const beforeIdx = rendered.indexOf("AGENT_BEFORE_RUN_UNIQUE");
	const runIdx = rendered.indexOf("Run #");
	const afterIdx = rendered.indexOf("AGENT_AFTER_RUN_UNIQUE");
	expect(beforeIdx).toBeGreaterThanOrEqual(0);
	expect(runIdx).toBeGreaterThan(beforeIdx);
	expect(afterIdx).toBeGreaterThan(runIdx);

	expectCleanConsole(problems);
});