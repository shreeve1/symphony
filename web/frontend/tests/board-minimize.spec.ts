import { expect, expectCleanConsole, test } from "./fixtures";

test("collapse and expand column", async ({ page, problems }) => {
	await page.goto("/trading");

	// Verify Todo column starts expanded.
	const todoCol = page.getByTestId("column-todo");
	await expect(todoCol).toBeVisible();
	await expect(todoCol).not.toHaveAttribute("data-collapsed");

	// Click minimize — column collapses to a narrow strip.
	await page.getByTestId("minimize-todo").click();
	await expect(todoCol).toHaveAttribute("data-collapsed", "true");
	await expect(page.getByTestId("count-todo")).toBeVisible();

	// Click expand — column restores.
	await page.getByTestId("expand-todo").click();
	await expect(todoCol).not.toHaveAttribute("data-collapsed");
	await expect(page.getByTestId("minimize-todo")).toBeVisible();

	expectCleanConsole(problems);
});

test("collapse state persists on reload", async ({ page, problems }) => {
	await page.goto("/trading");

	// Collapse Todo.
	await page.getByTestId("minimize-todo").click();
	await expect(page.getByTestId("column-todo")).toHaveAttribute(
		"data-collapsed",
		"true",
	);

	// Reload.
	await page.reload();
	await expect(page.getByTestId("column-todo")).toHaveAttribute(
		"data-collapsed",
		"true",
	);

	expectCleanConsole(problems);
});

test("per-binding independence", async ({ page, problems }) => {
	// Collapse Todo on trading.
	await page.goto("/trading");
	await page.getByTestId("minimize-todo").click();
	await expect(page.getByTestId("column-todo")).toHaveAttribute(
		"data-collapsed",
		"true",
	);

	// Navigate to homelab — Todo column stays expanded (different binding key).
	await page.goto("/homelab");
	await expect(page.getByTestId("column-todo")).not.toHaveAttribute(
		"data-collapsed",
	);

	// Navigate back to trading — Todo column remembered as collapsed.
	await page.goto("/trading");
	await expect(page.getByTestId("column-todo")).toHaveAttribute(
		"data-collapsed",
		"true",
	);

	expectCleanConsole(problems);
});

test("corrupt collapse storage falls back to expanded", async ({ page, problems }) => {
	await page.addInitScript(() => {
		localStorage.setItem("podium.collapsed.trading", "not-json");
	});

	await page.goto("/trading");
	await expect(page.getByTestId("column-todo")).not.toHaveAttribute(
		"data-collapsed",
	);

	expectCleanConsole(problems);
});
