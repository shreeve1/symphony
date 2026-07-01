import type { Page } from "@playwright/test";

import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

// dnd-kit's PointerSensor has a 5px activation distance, so a real drag needs
// a pointer-down, several incremental moves past the threshold, then a move
// over the target column before the pointer-up. A single dragTo won't trip it.
async function dragCardToColumn(
	page: Page,
	cardTitle: string,
	targetColKey: string,
) {
	const card = page
		.getByTestId("issue-card")
		.filter({ hasText: cardTitle });
	const target = page.getByTestId(`column-${targetColKey}`);

	const cardBox = await card.boundingBox();
	const targetBox = await target.boundingBox();
	if (!cardBox || !targetBox) throw new Error("card or target not visible");

	const startX = cardBox.x + cardBox.width / 2;
	const startY = cardBox.y + cardBox.height / 2;
	const endX = targetBox.x + targetBox.width / 2;
	const endY = targetBox.y + targetBox.height / 2;

	await page.mouse.move(startX, startY);
	await page.mouse.down();
	// Cross the activation distance, then glide to the target column.
	await page.mouse.move(startX + 12, startY + 12, { steps: 6 });
	await page.mouse.move(endX, endY, { steps: 12 });
	await page.mouse.move(endX, endY);
	await page.mouse.up();
}

test("dragging a card to another column changes and persists its state", async ({
	page,
	problems,
}) => {
	const { issueId } = seedIssue("dotfiles", "Drag me across");

	await page.goto("/dotfiles");

	const todoCard = page
		.getByTestId("column-todo")
		.getByTestId("issue-card")
		.filter({ hasText: "Drag me across" });
	await expect(todoCard).toBeVisible();

	await dragCardToColumn(page, "Drag me across", "in_review");

	// The drop fires the same PATCH the state chip uses.
	await page.waitForResponse(
		(res) =>
			res.url().includes(`/api/issues/${issueId}`) &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

	// Card now lives in In Review, no longer in Todo.
	await expect(
		page
			.getByTestId("column-in_review")
			.getByTestId("issue-card")
			.filter({ hasText: "Drag me across" }),
	).toBeVisible();
	await expect(todoCard).not.toBeVisible();

	expectCleanConsole(problems);
});

test("clicking a card still opens the flyout after drag wiring", async ({
	page,
	problems,
}) => {
	seedIssue("dotfiles", "Click not drag");

	await page.goto("/dotfiles");

	// A plain click stays under the activation distance, so it must open the
	// flyout rather than starting a drag.
	await page
		.getByTestId("issue-card")
		.filter({ hasText: "Click not drag" })
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	expectCleanConsole(problems);
});
