import { expect, expectCleanConsole, test } from "./fixtures";

// Automation fixture data matching the backend contract.
const FIXTURES = {
	spawn: {
		id: 1,
		binding_name: "homelab",
		mode: "spawn" as const,
		enabled: true,
		template_title: "Patrol check {{date}}",
		template_body: "Run standard infra patrol.",
		spawn_interval_seconds: 3600,
		spawn_run_count: 10,
		occurrences_fired: 3,
		next_fire_at: new Date(Date.now() + 1800_000).toISOString(),
		loop_iteration_cap: null,
		loop_completion_marker: "DONE.md",
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
	loop: {
		id: 2,
		binding_name: "dotfiles",
		mode: "loop" as const,
		enabled: true,
		template_title: "Refactor pass on {{module}}",
		template_body: "Improve structure.",
		spawn_interval_seconds: null,
		spawn_run_count: null,
		occurrences_fired: 5,
		next_fire_at: null,
		loop_iteration_cap: 20,
		loop_completion_marker: "DONE.md",
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
	disabled: {
		id: 3,
		binding_name: "homelab",
		mode: "spawn" as const,
		enabled: false,
		template_title: "Nightly cleanup",
		template_body: "Clean temp files.",
		spawn_interval_seconds: 86400,
		spawn_run_count: null,
		occurrences_fired: 0,
		next_fire_at: null,
		loop_iteration_cap: null,
		loop_completion_marker: "DONE.md",
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
};

test.describe("Automations page", () => {
	test("sidebar shows Automations link for active binding", async ({
		page,
	}) => {
		await page.goto("/homelab");

		// Click binding row to make it active — sub-links appear.
		await page
			.getByTestId("binding-row")
			.filter({ hasText: "homelab" })
			.click();
		await expect(page).toHaveURL("/homelab");

		// Files link is the existing one; Automations should be right alongside.
		await expect(page.getByTestId("binding-files-link")).toBeVisible();
		await expect(page.getByTestId("binding-automations-link")).toBeVisible();
		await expect(page.getByTestId("binding-automations-link")).toHaveText(
			"Automations",
		);
	});

	test("navigates to automations page and lists automations", async ({
		page,
		problems,
	}) => {
		// Mock the automations list endpoint.
		await page.route("**/api/bindings/homelab/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify([FIXTURES.spawn, FIXTURES.disabled]),
			});
		});

		await page.goto("/homelab/automations");
		await expect(page.getByTestId("automations-page")).toBeVisible();
		await expect(page.getByTestId("automations-page")).toContainText(
			"Automations",
		);

		// Both automations render as rows in the list.
		const rows = page.getByTestId("automation-row");
		await expect(rows).toHaveCount(2);

		// Spawn row shows mode, enabled state, interval, count.
		const spawnRow = rows.filter({ hasText: "Patrol check" });
		await expect(spawnRow.getByTestId("automation-mode")).toHaveText("spawn");
		await expect(spawnRow.getByTestId("automation-enabled")).toBeVisible();
		await expect(spawnRow.getByTestId("automation-next-fire")).toBeVisible();
		await expect(spawnRow.getByTestId("automation-remaining")).toContainText(
			"7",
		);

		// Disabled row shows disabled state.
		const disabledRow = rows.filter({ hasText: "Nightly" });
		await expect(
			disabledRow.getByTestId("automation-enabled"),
		).not.toBeChecked();
		await expect(disabledRow.getByTestId("automation-remaining")).toContainText(
			"Unlimited",
		);

		expectCleanConsole(problems);
	});

	test("shows a loop cap without using spawn occurrence counts", async ({
		page,
		problems,
	}) => {
		await page.route("**/api/bindings/dotfiles/automations", (route) =>
			route.fulfill({ status: 200, json: [FIXTURES.loop] }),
		);

		await page.goto("/dotfiles/automations");
		await expect(page.getByTestId("automation-remaining")).toHaveText("Cap 20");
		expectCleanConsole(problems);
	});

	test("creates a new spawn automation", async ({ page, problems }) => {
		const created: object[] = [];
		let postedInterval: number | undefined;
		let postedDelay: number | undefined;
		await page.route("**/api/bindings/homelab/automations", (route) => {
			if (route.request().method() === "GET") {
				route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify(created),
				});
			} else if (route.request().method() === "POST") {
				const body = JSON.parse(route.request().postData() ?? "{}");
				postedInterval = body.spawn_interval_seconds;
				postedDelay = body.start_delay_seconds;
				const row = {
					id: 10,
					...body,
					occurrences_fired: 0,
					next_fire_at: null,
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString(),
				};
				created.push(row);
				route.fulfill({
					status: 201,
					contentType: "application/json",
					body: JSON.stringify(row),
				});
			} else {
				route.continue();
			}
		});

		await page.goto("/homelab/automations");
		await expect(page.getByTestId("automations-page")).toBeVisible();

		// Click create button → form appears.
		await page.getByTestId("automation-create-btn").click();
		await expect(page.getByTestId("automation-form")).toBeVisible();

		// Fill spawn form.
		await page.getByTestId("automation-form-title").fill("Nightly patrol");
		await page
			.getByTestId("automation-form-body")
			.fill("Run checks every night.");
		// Interval is entered in minutes; the payload converts to seconds.
		await page.getByTestId("automation-form-interval").fill("120");
		// Leave count empty → unlimited.
		// Issue #462: uncheck "Start immediately" to enable the initial delay,
		// entered in minutes and converted to seconds in the payload.
		await page.getByTestId("automation-form-start-now").uncheck();
		await page.getByTestId("automation-form-delay").fill("60");

		// Submit.
		await page.getByTestId("automation-form-submit").click();
		await expect(page.getByTestId("automation-form")).toBeHidden();
		await expect(page.getByTestId("automation-row")).toHaveCount(1);
		expect(postedInterval).toBe(7200); // 120 min × 60
		expect(postedDelay).toBe(3600); // 60 min × 60

		expectCleanConsole(problems);
	});

	test("omits start_delay_seconds when starting immediately", async ({
		page,
		problems,
	}) => {
		const created: object[] = [];
		let postedBody: Record<string, unknown> = {};
		await page.route("**/api/bindings/homelab/automations", (route) => {
			if (route.request().method() === "GET") {
				route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify(created),
				});
			} else if (route.request().method() === "POST") {
				postedBody = JSON.parse(route.request().postData() ?? "{}");
				const row = {
					id: 11,
					...postedBody,
					occurrences_fired: 0,
					next_fire_at: null,
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString(),
				};
				created.push(row);
				route.fulfill({
					status: 201,
					contentType: "application/json",
					body: JSON.stringify(row),
				});
			} else {
				route.continue();
			}
		});

		await page.goto("/homelab/automations");
		await expect(page.getByTestId("automations-page")).toBeVisible();
		await page.getByTestId("automation-create-btn").click();
		await expect(page.getByTestId("automation-form")).toBeVisible();
		await page.getByTestId("automation-form-title").fill("Immediate patrol");
		await page.getByTestId("automation-form-body").fill("Run now.");
		await page.getByTestId("automation-form-interval").fill("15");
		// "Start immediately" is checked by default → delay field disabled.
		await expect(page.getByTestId("automation-form-delay")).toBeDisabled();
		await page.getByTestId("automation-form-submit").click();
		await expect(page.getByTestId("automation-form")).toBeHidden();
		expect(postedBody.start_delay_seconds).toBeUndefined();

		expectCleanConsole(problems);
	});

	test("edits an automation", async ({ page, problems }) => {
		let automation = { ...FIXTURES.spawn };
		let patchCalled = false;
		await page.route("**/api/bindings/homelab/automations**", (route) => {
			if (route.request().method() === "PATCH") {
				patchCalled = true;
				automation = {
					...automation,
					...JSON.parse(route.request().postData() ?? "{}"),
				};
				return route.fulfill({ status: 200, json: automation });
			}
			if (route.request().method() === "GET") {
				return route.fulfill({ status: 200, json: [automation] });
			}
			return route.fulfill({ status: 405 });
		});

		await page.goto("/homelab/automations");
		await page.getByTestId("automation-edit-btn").click();
		await page.getByTestId("automation-form-title").fill("Updated patrol");
		await page.getByTestId("automation-form-submit").click();

		await expect.poll(() => patchCalled).toBe(true);
		await expect(page.getByTestId("automation-row")).toContainText(
			"Updated patrol",
		);
		expectCleanConsole(problems);
	});

	test("toggles automation enable/disable", async ({ page, problems }) => {
		let automations = [{ ...FIXTURES.spawn, enabled: true }];
		await page.route("**/api/bindings/homelab/automations**", (route) => {
			const url = route.request().url();
			// PATCH /api/bindings/{binding}/automations/{id}
			if (route.request().method() === "PATCH") {
				const id = parseInt(url.split("/").pop()!, 10);
				const body = JSON.parse(route.request().postData() ?? "{}");
				automations = automations.map((a) =>
					a.id === id ? { ...a, ...body } : a,
				);
				route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify(automations.find((a) => a.id === id)),
				});
			} else if (route.request().method() === "GET") {
				route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify(automations),
				});
			} else {
				route.continue();
			}
		});

		await page.goto("/homelab/automations");
		await expect(page.getByTestId("automation-row")).toHaveCount(1);

		// Initially enabled.
		const toggle = page.getByTestId("automation-enabled");
		await expect(toggle).toBeChecked();

		// Click to disable.
		await toggle.click();
		await expect(page.getByTestId("automation-enabled")).not.toBeChecked();

		// Re-enable.
		await toggle.click();
		await expect(page.getByTestId("automation-enabled")).toBeChecked();

		expectCleanConsole(problems);
	});

	test("deletes an automation", async ({ page, problems }) => {
		let automations = [{ ...FIXTURES.spawn }];
		await page.route("**/api/bindings/homelab/automations/**", (route) => {
			if (route.request().method() === "DELETE") {
				automations = [];
				route.fulfill({ status: 204 });
			} else {
				route.continue();
			}
		});
		await page.route("**/api/bindings/homelab/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify(automations),
			});
		});

		await page.goto("/homelab/automations");
		await expect(page.getByTestId("automation-row")).toHaveCount(1);

		// Click delete → confirm.
		page.once("dialog", (d) => d.accept());
		await page.getByTestId("automation-delete-btn").click();
		await expect(page.getByTestId("automation-row")).toHaveCount(0);

		expectCleanConsole(problems);
	});

	test("loop option is hidden on infra binding", async ({ page, problems }) => {
		// Mock automations list to avoid 404 console error.
		await page.route("**/api/bindings/homelab/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		await page.goto("/homelab/automations");
		await page.getByTestId("automation-create-btn").click();
		await expect(page.getByTestId("automation-form")).toBeVisible();

		// Mode selector should only have 'spawn' for homelab (infra).
		await expect(page.getByTestId("automation-form-mode")).toBeVisible();
		const options = page.getByTestId("automation-form-mode").locator("option");
		await expect(options).toHaveCount(1);
		await expect(options.first()).toHaveValue("spawn");

		expectCleanConsole(problems);
	});

	test("loop option is visible on coding binding", async ({
		page,
		problems,
	}) => {
		// Mock automations list to avoid 404 console error.
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();
		await expect(page.getByTestId("automation-form")).toBeVisible();

		// Mode selector for coding binding shows both spawn and loop.
		const options = page.getByTestId("automation-form-mode").locator("option");
		await expect(options).toHaveCount(2);
		await expect(options.nth(0)).toHaveValue("spawn");
		await expect(options.nth(1)).toHaveAttribute("value", "loop");

		expectCleanConsole(problems);
	});

	test("delayed start requires a positive delay (#462)", async ({
		page,
		problems,
	}) => {
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();
		await page.getByTestId("automation-form-title").fill("Delayed patrol");
		await page.getByTestId("automation-form-body").fill("Run later.");
		await page.getByTestId("automation-form-interval").fill("15");

		// Submit enabled while "Start immediately" is checked (default).
		await expect(page.getByTestId("automation-form-submit")).toBeEnabled();

		// Uncheck → delay field enabled but empty → submit blocked.
		await page.getByTestId("automation-form-start-now").uncheck();
		await expect(page.getByTestId("automation-form-delay")).toBeEnabled();
		await expect(page.getByTestId("automation-form-submit")).toBeDisabled();

		// Enter a positive delay → submit re-enabled.
		await page.getByTestId("automation-form-delay").fill("60");
		await expect(page.getByTestId("automation-form-submit")).toBeEnabled();

		expectCleanConsole(problems);
	});

	test("loop form shows iteration cap and marker; spawn form shows interval and count", async ({
		page,
		problems,
	}) => {
		// Mock automations list to avoid 404 console error.
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();

		// Default mode is spawn — spawn fields visible, loop fields hidden.
		await expect(page.getByTestId("automation-form-interval")).toBeVisible();
		await expect(page.getByTestId("automation-form-count")).toBeVisible();
		await expect(
			page.getByTestId("automation-form-iter-cap"),
		).not.toBeVisible();
		await expect(page.getByTestId("automation-form-marker")).not.toBeVisible();

		// Switch to loop.
		await page.getByTestId("automation-form-mode").selectOption("loop");
		await expect(
			page.getByTestId("automation-form-interval"),
		).not.toBeVisible();
		await expect(page.getByTestId("automation-form-count")).not.toBeVisible();
		await expect(page.getByTestId("automation-form-iter-cap")).toBeVisible();
		await expect(page.getByTestId("automation-form-marker")).toBeVisible();

		expectCleanConsole(problems);
	});

	test("skill/agent/model pin fields are shown inline by default (#462)", async ({
		page,
		problems,
	}) => {
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();

		// Pin section is front-and-center: visible immediately, no toggle.
		await expect(page.getByTestId("automation-form-pins")).toBeVisible();
		await expect(
			page.getByTestId("automation-form-pins-toggle"),
		).not.toBeVisible();
		await expect(page.getByTestId("automation-form-pin-skill")).toBeVisible();
		await expect(page.getByTestId("automation-form-pin-agent")).toBeVisible();
		await expect(page.getByTestId("automation-form-pin-model")).toBeVisible();

		// Spawn mode shows the worktree checkbox; loop mode hides it.
		await expect(
			page.getByTestId("automation-form-pin-worktree"),
		).toBeVisible();
		await page.getByTestId("automation-form-mode").selectOption("loop");
		await expect(
			page.getByTestId("automation-form-pin-worktree"),
		).not.toBeVisible();

		expectCleanConsole(problems);
	});

	test("model options filter to the selected agent and empty catalog hints (#462)", async ({
		page,
		problems,
	}) => {
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		// Empty skill catalog → the operator gets a refresh hint instead of a
		// silent empty dropdown.
		await page.route("**/api/skills**", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: "[]",
			});
		});
		await page.route("**/api/bindings/dotfiles/options", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify({
					agents: ["pi", "claude"],
					models: [
						{ id: "Duo", agent: "pi", provider: "pi-duo" },
						{ id: "Sonnet", agent: "claude", provider: "anthropic" },
					],
					branches: [],
				}),
			});
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();

		await expect(
			page.getByTestId("automation-skill-catalog-empty"),
		).toBeVisible();

		// No agent picked → both models offered.
		await page.getByTestId("automation-form-pin-model").click();
		await expect(
			page.getByTestId("automation-form-pin-model-option"),
		).toHaveCount(3); // empty sentinel + 2 models

		// Pick the pi agent → only the pi model remains selectable.
		await page.getByTestId("automation-form-pin-agent").click();
		await page
			.getByTestId("automation-form-pin-agent-option")
			.filter({ hasText: "pi" })
			.first()
			.click();
		await page.getByTestId("automation-form-pin-model").click();
		await expect(
			page.getByTestId("automation-form-pin-model-option"),
		).toHaveCount(2); // empty sentinel + pi-duo/Duo only

		expectCleanConsole(problems);
	});

	test("list shows 'pinned' badge when an automation has any pin field set (#459)", async ({
		page,
		problems,
	}) => {
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify([
					{
						id: 1,
						binding_name: "dotfiles",
						mode: "spawn",
						enabled: true,
						template_title: "Pinned automation",
						template_body: "With model pin",
						spawn_interval_seconds: 3600,
						spawn_run_count: null,
						occurrences_fired: 0,
						next_fire_at: null,
						loop_iteration_cap: null,
						loop_completion_marker: "DONE.md",
						preferred_skill: null,
						preferred_agent: null,
						preferred_model: "pi-duo/Duo",
						reasoning_effort: null,
						base_branch: null,
						worktree_active: false,
						created_at: "2026-07-17T00:00:00+00:00",
						updated_at: "2026-07-17T00:00:00+00:00",
					},
					{
						id: 2,
						binding_name: "dotfiles",
						mode: "spawn",
						enabled: true,
						template_title: "Unpinned automation",
						template_body: "Plain",
						spawn_interval_seconds: 3600,
						spawn_run_count: null,
						occurrences_fired: 0,
						next_fire_at: null,
						loop_iteration_cap: null,
						loop_completion_marker: "DONE.md",
						preferred_skill: null,
						preferred_agent: null,
						preferred_model: null,
						reasoning_effort: null,
						base_branch: null,
						worktree_active: false,
						created_at: "2026-07-17T00:00:00+00:00",
						updated_at: "2026-07-17T00:00:00+00:00",
					},
				]),
			});
		});
		await page.goto("/dotfiles/automations");
		const pinnedRow = page.getByTestId("automation-row").first();
		await expect(pinnedRow.getByTestId("automation-pins-badge")).toBeVisible();
		const unpinnedRow = page.getByTestId("automation-row").nth(1);
		await expect(
			unpinnedRow.getByTestId("automation-pins-badge"),
		).not.toBeVisible();

		expectCleanConsole(problems);
	});
});
