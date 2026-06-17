import type { Page } from "@playwright/test";
import { expect, expectCleanConsole, seedIssue, test } from "./fixtures";

const RUN_ID = Date.now();
const QUEUED_TITLE = `Dashboard queued issue ${RUN_ID}`;
const DONE_TITLE = `Dashboard done issue ${RUN_ID}`;
const ARCHIVED_TITLE = `Dashboard archived issue ${RUN_ID}`;
const ACTIVE_DASHBOARD_STATES = new Set([
	"todo",
	"running",
	"in_review",
	"blocked",
]);

async function fetchDashboardTotal(page: Page): Promise<number> {
	const bindingsResponse = await page.request.get("/api/bindings");
	expect(bindingsResponse.ok()).toBeTruthy();
	const bindings = (await bindingsResponse.json()) as {
		name: string;
		archived: boolean;
	}[];

	let total = 0;
	for (const binding of bindings.filter((b) => !b.archived)) {
		const issuesResponse = await page.request.get(
			`/api/bindings/${encodeURIComponent(binding.name)}/issues`,
		);
		expect(issuesResponse.ok()).toBeTruthy();
		const issues = (await issuesResponse.json()) as { state: string }[];
		total += issues.filter((issue) =>
			ACTIVE_DASHBOARD_STATES.has(issue.state),
		).length;
	}
	return total;
}

test("dashboard shows per-binding cards and global roll-up", async ({
	page,
	problems,
}) => {
	// Seed active and terminal issues so the dashboard total can prove terminal
	// states are omitted from the roll-up.
	seedIssue("homelab", QUEUED_TITLE, "todo");
	seedIssue("homelab", DONE_TITLE, "done");
	seedIssue("homelab", ARCHIVED_TITLE, "archived");
	const expectedTotal = await fetchDashboardTotal(page);

	await page.goto("/");

	// Global roll-up visible and terminal states omitted.
	const rollup = page.getByTestId("dashboard-global-rollup");
	await expect(rollup).toBeVisible();
	await expect(rollup).toContainText(`${expectedTotal} issues`);
	await expect(rollup).not.toContainText("Done");
	await expect(rollup).not.toContainText("Archived");

	// Per-binding cards for non-archived bindings.
	const homelabCard = page.getByTestId("dashboard-binding-homelab");
	const symphonyCard = page.getByTestId("dashboard-binding-symphony");
	await expect(homelabCard).toBeVisible();
	await expect(symphonyCard).toBeVisible();

	// Cards still show active states while terminal state badges are omitted.
	await expect(homelabCard).toContainText("Todo");
	await expect(homelabCard).toContainText("Running");
	await expect(homelabCard).not.toContainText("Done");
	await expect(homelabCard).not.toContainText("Archived");

	await expect(page.getByTestId("dashboard-attention")).toHaveCount(0);
	await expect(page.getByTestId("attention-row")).toHaveCount(0);

	expectCleanConsole(problems, {
		ignore: [/ERR_ABORTED/],
	});
});
