import type { Page } from "@playwright/test";

import { authenticate, expect, expectCleanConsole, test } from "./fixtures";

const LIVE_SYNC_CARD = "Seed todo issue for homelab";

async function openIssue(page: Page, title: string) {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();
}

const waitForPatch = (page: Page) =>
	page.waitForResponse(
		(res) =>
			res.url().includes("/api/issues/") &&
			res.request().method() === "PATCH" &&
			res.ok(),
	);

test("live issue updates sync between browser contexts", async ({
	browser,
	page,
	problems,
}) => {
	const other = await browser.newPage();
	await authenticate(other);
	const otherProblems: string[] = [];
	other.on("console", (msg) => {
		if (msg.type() === "error")
			otherProblems.push(`console.error: ${msg.text()}`);
	});
	other.on("pageerror", (err) =>
		otherProblems.push(`pageerror: ${err.message}`),
	);
	other.on("requestfailed", (req) => {
		const failure = req.failure()?.errorText ?? "unknown";
		otherProblems.push(
			`requestfailed: ${req.method()} ${req.url()} (${failure})`,
		);
	});
	other.on("response", (res) => {
		if (res.status() >= 400) {
			otherProblems.push(
				`httperror: ${res.status()} ${res.request().method()} ${res.url()}`,
			);
		}
	});

	try {
		await openIssue(page, LIVE_SYNC_CARD);
		await openIssue(other, LIVE_SYNC_CARD);

		const state = page.getByTestId("edit-state");
		const nextState =
			(await state.inputValue()) === "blocked" ? "todo" : "blocked";
		const patched = waitForPatch(page);
		await state.selectOption(nextState);
		await patched;

		await expect(other.getByTestId("edit-state")).toHaveValue(nextState, {
			timeout: 3_000,
		});
	} finally {
		await other.close();
	}

	expectCleanConsole(problems);
	expect(otherProblems).toEqual([]);
});

test("disconnected pill renders while websocket reconnects", async ({
	context,
	page,
	problems,
}) => {
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();

	await context.setOffline(true);
	await expect(page.getByTestId("connection-pill")).toContainText(
		"Disconnected — retrying",
	);

	await context.setOffline(false);
	await expect(page.getByTestId("connection-pill")).toBeHidden({
		timeout: 5_000,
	});

	expectCleanConsole(problems, { ignore: [/ERR_INTERNET_DISCONNECTED/] });
});
