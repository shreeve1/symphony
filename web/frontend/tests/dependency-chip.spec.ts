import { expect, expectCleanConsole, test, type PageProblems } from "./fixtures";

async function createIssue(page: any, body: Record<string, unknown>) {
	const response = await page.request.post("/api/bindings/symphony/issues", {
		data: body,
	});
	expect(response.ok()).toBeTruthy();
	return (await response.json()) as { id: number };
}

test("todo cards show dependency and lock gate chips", async ({
	page,
	problems,
}: {
	page: any;
	problems: PageProblems;
}) => {
	const parent = await createIssue(page, { title: "Dependency chip parent" });
	const child = await createIssue(page, {
		title: "Dependency chip child",
		blocked_by: [parent.id],
	});
	const running = await createIssue(page, {
		title: "Dependency chip running lock holder",
		locks: ["scheduler"],
	});
	await page.request.patch(`/api/issues/${running.id}`, {
		data: { state: "running" },
	});
	const locked = await createIssue(page, {
		title: "Dependency chip locked todo",
		locks: ["scheduler"],
	});

	await page.goto("/symphony");

	const childCard = page
		.getByTestId("issue-card")
		.filter({ hasText: "Dependency chip child" });
	await expect(childCard.getByTestId("waiting-chip")).toHaveText(
		`Waiting on #${parent.id}`,
	);

	const lockedCard = page
		.getByTestId("issue-card")
		.filter({ hasText: "Dependency chip locked todo" });
	await expect(lockedCard.getByTestId("lock-chip")).toHaveText(
		"Locked: scheduler",
	);
	await lockedCard.click();
	await expect(page.getByTestId("issue-flyout").getByTestId("lock-chip")).toHaveText(
		"Locked: scheduler",
	);

	await page.request.patch(`/api/issues/${parent.id}`, { data: { state: "done" } });
	await expect(childCard.getByTestId("waiting-chip")).toHaveCount(0);

	await page.request.patch(`/api/issues/${running.id}`, { data: { state: "done" } });
	await expect(lockedCard.getByTestId("lock-chip")).toHaveCount(0);
	await expect(page.getByTestId("issue-flyout").getByTestId("lock-chip")).toHaveCount(0);

	expect(child.id).toBeGreaterThan(parent.id);
	expect(locked.id).toBeGreaterThan(running.id);
	expectCleanConsole(problems);
});
