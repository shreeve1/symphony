import {
	test,
	expect,
	appendSessionTail,
	seedIssue,
	seedSkills,
	seedRunningRunIssue,
} from "./fixtures";

test("session tail tab renders empty placeholder when no run is active", async ({
	page,
}) => {
	// Seed an issue that has no runs at all — the seed issues all carry a
	// succeeded seed run, and SessionTailPanel renders the terminal bubble
	// (not the empty placeholder) whenever any finished run exists.
	const title = `e2e session tail empty ${Date.now()}`;
	seedIssue("homelab", title);

	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();

	await page
		.getByTestId("issue-card")
		.filter({ hasText: title })
		.first()
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Click the session tab
	await page.getByTestId("tab-session").click();

	// Should show empty placeholder since no running session
	await expect(page.getByTestId("session-tail-empty")).toBeVisible();
	await expect(page.getByTestId("session-tail-empty")).toContainText(
		"No active session",
	);
});

test("session tail batches a burst in order without duplicate lines", async ({
	page,
}) => {
	const title = `e2e session tail burst ${Date.now()}`;
	const { issueId } = seedRunningRunIssue("homelab", title);

	await page.addInitScript(() => {
		const original = window.requestAnimationFrame.bind(window);
		let calls = 0;
		window.requestAnimationFrame = (callback) => {
			calls += 1;
			return original(callback);
		};
		Object.defineProperty(window, "__tailRafCalls", { get: () => calls });
		Object.defineProperty(window, "__releaseTailFrame", {
			value: () => new Promise<void>((resolve) => original(() => resolve())),
		});
	});
	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();
	await page.getByTestId("issue-card").filter({ hasText: title }).click();
	await page.getByTestId("tab-session").click();

	for (const content of ["burst one", "burst two", "burst three"]) {
		appendSessionTail(issueId, { type: "assistant", content });
	}

	await expect(page.getByTestId("session-tail-line")).toHaveText([
		/"content": "burst one"/,
		/"content": "burst two"/,
		/"content": "burst three"/,
	]);
	await expect
		.poll(() =>
			page.evaluate(
				() =>
					(window as typeof window & { __tailRafCalls: number }).__tailRafCalls,
			),
		)
		.toBeGreaterThan(0);
	await page.evaluate(() =>
		(
			window as typeof window & { __releaseTailFrame: () => Promise<void> }
		).__releaseTailFrame(),
	);
});

test("session tail tab shows live lines for a running issue", async ({
	page,
}) => {
	seedSkills([{ name: "blueprint" }, { name: "code-review" }]);

	const title = `e2e session tail issue ${Date.now()}`;
	const { issueId } = seedRunningRunIssue("homelab", title);

	await page.goto("/homelab");
	await expect(page.getByTestId("connection-pill")).toBeHidden();

	await page
		.getByTestId("issue-card")
		.filter({ hasText: title })
		.first()
		.click();
	await expect(page.getByTestId("issue-flyout")).toBeVisible();

	// Switch to the session tab.
	await page.getByTestId("tab-session").click();

	// Should show empty placeholder until the session file receives content.
	await expect(page.getByTestId("session-tail-empty")).toBeVisible();

	appendSessionTail(issueId, {
		type: "assistant",
		content: "live tail smoke line",
	});

	await expect(page.getByTestId("session-tail-line")).toContainText(
		"live tail smoke line",
	);
});
