import type { Page } from "@playwright/test";

import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

async function openPage(page: Page) {
	await page.goto("/");
	await expect(page.getByTestId("connection-pill")).toBeHidden();
}

const waitForReply = (page: Page) =>
	page.waitForResponse(
		(res) =>
			/\/api\/issues\/\d+\/reply$/.test(res.url()) &&
			res.request().method() === "POST" &&
			res.ok(),
	);

// Run inbox tests serially so they don't fight over the shared e2e DB.
test.describe
	.serial("inbox", () => {
		test("inbox section absent when empty", async ({ page, problems }) => {
			await openPage(page);
			// No "Inbox" label when there are no qualifying issues.
			await expect(
				page.getByTestId("sidebar").getByText(/^Inbox \(/),
			).toHaveCount(0);
			expectCleanConsole(problems);
		});

		test("inbox section visible with count and cards when non-empty", async ({
			page,
			problems,
		}) => {
			const title = `e2e inbox card ${Date.now()}`;
			seedIssue("homelab", title, "in_review");

			await openPage(page);

			// Card becomes visible (inbox polls every 10s).
			const card = page.getByTestId("inbox-card").filter({ hasText: title });
			await expect(card).toBeVisible({ timeout: 15_000 });

			// State badge is visible.
			await expect(card).toContainText("In Review");

			// Binding color dot is present (a small span with background color).
			await expect(card.locator("span").first()).toBeVisible();

			// Relative age is shown (m, h, d, or "now").
			await expect(card.getByText(/^(now|\d+[mhd])$/)).toBeVisible();

			// Inbox section header appears with non-zero count.
			const header = page.getByTestId("sidebar").getByText(/^Inbox \(\d+\)$/);
			await expect(header).toBeVisible();

			expectCleanConsole(problems);
		});

		test("clicking inbox card navigates and opens flyout", async ({
			page,
			problems,
		}) => {
			const title = `e2e inbox nav ${Date.now()}`;
			const { issueId } = seedIssue("homelab", title, "in_review");

			await openPage(page);

			// Wait for inbox card to appear.
			const card = page.getByTestId("inbox-card").filter({ hasText: title });
			await expect(card).toBeVisible({ timeout: 15_000 });

			// Click the card.
			await card.click();

			// URL is /homelab?issue={id}.
			await expect(page).toHaveURL(`/homelab?issue=${issueId}`);

			// Flyout opens.
			await expect(page.getByTestId("issue-flyout")).toBeVisible();

			expectCleanConsole(problems);
		});

		test("operator reply removes inbox card", async ({ page, problems }) => {
			const title = `e2e inbox reply remove ${Date.now()}`;
			seedIssue("homelab", title, "in_review");

			await openPage(page);

			// Wait for inbox card to appear.
			const card = page.getByTestId("inbox-card").filter({ hasText: title });
			await expect(card).toBeVisible({ timeout: 15_000 });

			// Navigate to the issue via inbox click.
			await card.click();
			await expect(page.getByTestId("issue-flyout")).toBeVisible();

			// Post a reply.
			const input = page.getByTestId("reply-input");
			await expect(input).toBeVisible();
			await input.fill("Please continue.");
			const replied = waitForReply(page);
			await page.getByTestId("reply-send").click();
			await replied;

			// Card should disappear from inbox (reply flips state to todo).
			await expect(
				page.getByTestId("inbox-card").filter({ hasText: title }),
			).not.toBeVisible({ timeout: 15_000 });

			expectCleanConsole(problems);
		});
	});
