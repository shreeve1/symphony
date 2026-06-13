import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

test("archived column is collapsed by default on fresh binding", async ({
	page,
	problems,
}) => {
	// No localStorage set for this binding -> archived column default collapsed.
	await page.goto("/trading");

	const col = page.getByTestId("column-archived");
	await expect(col).toBeVisible();
	await expect(col).toHaveAttribute("data-collapsed", "true");

	expectCleanConsole(problems);
});

test("state chip moves issue to archived column", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue("trading", "Archive me");

	await page.goto("/trading");

	// Open flyout.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Archive me" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Archive via the state chip.
	await page.getByTestId("edit-state").selectOption("archived");

	// Wait for the PATCH to settle.
	await page.waitForResponse(
		(res) =>
			res.url().includes(`/api/issues/${issueId}`) &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

	// Card moved out of todo.
	await expect(
		page
			.getByTestId("column-todo")
			.getByTestId("issue-card")
			.filter({ hasText: "Archive me" }),
	).not.toBeVisible();

	// Close flyout so it doesn't block the expand button.
	await page.keyboard.press("Escape");
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	// Expand archived column to see the card there.
	const archivedCol = page.getByTestId("column-archived");
	await expect(archivedCol).toHaveAttribute("data-collapsed", "true");
	await page.getByTestId("expand-archived").click();
	await expect(archivedCol).not.toHaveAttribute("data-collapsed");

	await expect(
		archivedCol.getByTestId("issue-card").filter({ hasText: "Archive me" }),
	).toBeVisible();

	expectCleanConsole(problems);
});

test("state chip restores archived issue", async ({ page, problems }) => {
	const { issueId } = seedIssue("trading", "Restore me", "archived");

	await page.goto("/trading");

	// Expand archived column and open the issue.
	const archivedCol = page.getByTestId("column-archived");
	await page.getByTestId("expand-archived").click();

	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Restore me" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Use the state chip to change back to todo.
	const state = page.getByTestId("edit-state");
	await state.selectOption("todo");

	await page.waitForResponse(
		(res) =>
			res.url().includes(`/api/issues/${issueId}`) &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

	// Card is now in todo column.
	await expect(
		page
			.getByTestId("column-todo")
			.getByTestId("issue-card")
			.filter({ hasText: "Restore me" }),
	).toBeVisible();

	expectCleanConsole(problems);
});
