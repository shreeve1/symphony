import { expect, expectCleanConsole, seedSkills, test } from "./fixtures";

const waitForPatch = (page: import("@playwright/test").Page) =>
	page.waitForResponse(
		(res) =>
			res.url().includes("/api/issues/") &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

test("worktree chip renders path and clears after done", async ({
	page,
	problems,
}) => {
	seedSkills([{ name: "/dev-build", description: "Build e2e fixture" }]);
	const title = `e2e worktree issue ${Date.now()}`;

	await page.goto("/homelab");
	await page.getByTestId("new-issue-button").click();
	await expect(page.getByTestId("new-issue-modal")).toBeVisible();
	await page.getByTestId("new-issue-title").fill(title);
	await page.getByTestId("new-issue-worktree").check();

	const created = page.waitForResponse(
		(res) =>
			res.url().includes("/api/bindings/homelab/issues") &&
			res.request().method() === "POST" &&
			res.status() === 201,
	);
	await page.getByTestId("new-issue-submit").click();
	await created;

	const card = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: title });
	await expect(card).toBeVisible();
	await card.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await expect(page.getByTestId("edit-worktree_active")).toHaveAttribute(
		"aria-pressed",
		"true",
	);
	await expect(page.getByTestId("worktree-path")).toContainText(
		"worktrees/homelab/",
	);
	await expect(page.getByTestId("worktree-path")).toContainText("podium/homelab/");

	const patched = waitForPatch(page);
	await page.getByTestId("edit-state").selectOption("done");
	await patched;
	await expect(page.getByTestId("edit-state")).toHaveValue("done");
	await expect(page.getByTestId("worktree-path")).toHaveCount(0);

	expectCleanConsole(problems);
});
