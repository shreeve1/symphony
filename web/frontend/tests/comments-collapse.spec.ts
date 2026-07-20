import {
	expect,
	expectCleanConsole,
	seedIssue,
	setIssueComments,
	test,
} from "./fixtures";

test("comments tab shows the full chronological comments blob", async ({
	page,
	problems,
}) => {
	const title = `comments-chronology ${Date.now()}`;
	const { issueId } = seedIssue("dotfiles", title, "in_review");
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
	for (const entry of entries) {
		await expect(comments).toContainText(entry.split("\n\n")[1]);
	}
	const rendered = (await comments.textContent()) ?? "";
	const positions = entries.map((entry) =>
		rendered.indexOf(entry.split("\n\n")[1]),
	);
	expect(positions).toEqual([...positions].sort((a, b) => a - b));
	await expect(page.getByTestId("hidden-completions-note")).toHaveCount(0);

	expectCleanConsole(problems);
});
