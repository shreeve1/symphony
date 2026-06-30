import {
	expect,
	expectCleanConsole,
	seedWorktreeIssue,
	test,
	updateIssueState,
} from "./fixtures";

// The flyout surfaces the per-issue worktree path/branch for an active coding
// worktree, and hides it once the issue is done (the worktree is torn down on
// land). Regression guard for the path display removed in afb80c6 and restored
// when #108 made coding worktrees default-on.
test("flyout shows worktree path and clears after done", async ({
	page,
	problems,
}) => {
	const title = `e2e worktree issue ${Date.now()}`;
	const { issueId } = seedWorktreeIssue("symphony", title);

	await page.goto("/symphony");
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	const worktree = page.getByTestId("worktree-path");
	await expect(worktree).toContainText(`worktrees/symphony/${issueId}`);
	await expect(worktree).toContainText(`podium/symphony/${issueId}`);

	updateIssueState(issueId, "done");
	await page.reload();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("worktree-path")).toHaveCount(0);

	expectCleanConsole(problems);
});
