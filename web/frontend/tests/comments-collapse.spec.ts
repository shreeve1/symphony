import {
	expect,
	expectCleanConsole,
	seedIssue,
	setIssueComments,
	test,
} from "./fixtures";

// A multi-run conversation appends one `**Symphony completed:**` block per run,
// so the stored blob accumulates every completion. The Comments tab should show
// only the most recent completion (older ones stay in Run history) while
// keeping every operator reply.
test("comments tab collapses stacked completions to the most recent", async ({
	page,
	problems,
}) => {
	const title = `collapse-completions ${Date.now()}`;
	const { issueId } = seedIssue("trading", title, "in_review");
	setIssueComments(
		issueId,
		[
			"**Symphony completed:**\n\nFIRST_COMPLETION_UNIQUE work done.",
			"### Operator Reply (2026-06-18T13:00:00+00:00)\n\nOPERATOR_REPLY_UNIQUE keep going.",
			"**Symphony completed:**\n\nSECOND_COMPLETION_UNIQUE more work done.",
		].join("\n\n"),
	);

	await page.goto("/trading");
	await page
		.getByTestId("issue-card")
		.filter({ hasText: title })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const comments = page.getByTestId("view-comments_md");
	// Latest completion and the operator reply are shown.
	await expect(comments).toContainText("SECOND_COMPLETION_UNIQUE");
	await expect(comments).toContainText("OPERATOR_REPLY_UNIQUE");
	// The earlier completion is hidden, with a note pointing to Run history.
	await expect(comments).not.toContainText("FIRST_COMPLETION_UNIQUE");
	await expect(page.getByTestId("hidden-completions-note")).toContainText(
		"1 earlier Symphony completion hidden",
	);

	expectCleanConsole(problems);
});

// A patrol comment (ADR-0017 /comment primitive) is stamped `### Patrol (<ts>)`.
// It must split as its own entry and always show — never collapsed with agent
// summaries. Ordering matters for this assertion: the patrol block sits BETWEEN
// two completions, so without `### Patrol (` in ENTRY_BOUNDARY the patrol text
// would glue onto the earlier (collapsed) completion and vanish. Showing the
// patrol note while the older completion is hidden proves the boundary works.
test("comments tab keeps a patrol entry visible between collapsed completions", async ({
	page,
	problems,
}) => {
	const title = `patrol-entry ${Date.now()}`;
	const { issueId } = seedIssue("trading", title, "in_review");
	setIssueComments(
		issueId,
		[
			"**Symphony completed:**\n\nFIRST_COMPLETION_UNIQUE work done.",
			"### Patrol (2026-06-20T13:00:00+00:00)\n\nPATROL_NOTE_UNIQUE pass — 1/3.",
			"**Symphony completed:**\n\nSECOND_COMPLETION_UNIQUE more work done.",
		].join("\n\n"),
	);

	await page.goto("/trading");
	await page
		.getByTestId("issue-card")
		.filter({ hasText: title })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const comments = page.getByTestId("view-comments_md");
	// Patrol note and the latest completion show; the patrol entry is not folded
	// into the agent-summary collapse even though it sits next to completions.
	await expect(comments).toContainText("PATROL_NOTE_UNIQUE");
	await expect(comments).toContainText("SECOND_COMPLETION_UNIQUE");
	// The earlier completion is collapsed — confirming Patrol split it off rather
	// than being swept into the hidden block.
	await expect(comments).not.toContainText("FIRST_COMPLETION_UNIQUE");
	await expect(page.getByTestId("hidden-completions-note")).toContainText(
		"1 earlier Symphony completion hidden",
	);

	expectCleanConsole(problems);
});
