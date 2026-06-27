import type { Page } from "@playwright/test";

import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

async function openSeededIssue(page: Page, title: string) {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
}

test("done flyout closes only on returned done", async ({ page, problems }) => {
	// Flow 1: PATCH returns todo (dirty redispatch) → flyout stays open.
	const keepOpenTitle = `e2e edit-state keep-open ${Date.now()}`;
	const { issueId: keepOpenId } = seedIssue(
		"homelab",
		keepOpenTitle,
		"in_review",
	);

	await page.route("**/api/issues/*", async (route) => {
		if (route.request().method() !== "PATCH") return route.fallback();
		// Return todo — simulates dirty-redispatch from the backend.
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({
				id: keepOpenId,
				state: "todo",
				title: keepOpenTitle,
				binding_name: "homelab",
				binding_type: "coding",
				comments_md: "",
				context_md: "",
			}),
		});
	});

	await openSeededIssue(page, keepOpenTitle);
	await page.getByTestId("edit-state").selectOption("done");
	// Flyout must stay open because the returned state is "todo".
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	await page.unroute("**/api/issues/*");

	// Flow 2: PATCH returns done → flyout closes.
	const closeTitle = `e2e edit-state close ${Date.now()}`;
	const { issueId: closeId } = seedIssue("homelab", closeTitle, "in_review");

	await page.route("**/api/issues/*", async (route) => {
		if (route.request().method() !== "PATCH") return route.fallback();
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({
				id: closeId,
				state: "done",
				title: closeTitle,
				binding_name: "homelab",
				binding_type: "coding",
				comments_md: "",
				context_md: "",
			}),
		});
	});

	await page.goto("/homelab");
	await page.getByTestId("issue-card").filter({ hasText: closeTitle }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
	await page.getByTestId("edit-state").selectOption("done");
	await expect(page.getByTestId("issue-flyout")).toBeHidden();

	expectCleanConsole(problems);
});

test("active run 409 shows inline error", async ({ page, problems }) => {
	const title = `e2e edit-state 409 ${Date.now()}`;
	const { issueId } = seedIssue("homelab", title, "in_review");

	await page.route("**/api/issues/*", async (route) => {
		if (route.request().method() !== "PATCH") return route.fallback();
		return route.fulfill({
			status: 409,
			contentType: "application/json",
			body: JSON.stringify({
				detail: "land not allowed during active run running",
			}),
		});
	});

	await openSeededIssue(page, title);
	await page.getByTestId("edit-state").selectOption("done");

	// Flyout must stay open.
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Inline error must surface the 409 detail text.
	await expect(page.getByTestId("patch-error")).toBeVisible();
	await expect(page.getByTestId("patch-error")).toContainText(
		"land not allowed during active run running",
	);

	expectCleanConsole(problems, { ignore: [/409/] });
});
