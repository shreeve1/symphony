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
