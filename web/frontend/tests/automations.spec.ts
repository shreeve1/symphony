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
		await expect(
			page.getByTestId("binding-automations-link"),
		).toHaveText("Automations");
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
		await expect(
			disabledRow.getByTestId("automation-remaining"),
		).toContainText("Unlimited");

		expectCleanConsole(problems);
	});

	test("creates a new spawn automation", async ({ page, problems }) => {
		const created: object[] = [];
		await page.route("**/api/bindings/homelab/automations", (route) => {
			if (route.request().method() === "GET") {
				route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify(created),
				});
			} else if (route.request().method() === "POST") {
				const body = JSON.parse(route.request().postData() ?? "{}");
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
		await page.getByTestId("automation-form-interval").fill("7200");
		// Leave count empty → unlimited.

		// Submit.
		await page.getByTestId("automation-form-submit").click();
		await expect(page.getByTestId("automation-form")).toBeHidden();
		await expect(page.getByTestId("automation-row")).toHaveCount(1);

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
		await expect(page.getByTestId("automation-row")).toContainText("Updated patrol");
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
			route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
		});
		await page.goto("/homelab/automations");
		await page.getByTestId("automation-create-btn").click();
		await expect(page.getByTestId("automation-form")).toBeVisible();

		// Mode selector should only have 'spawn' for homelab (infra).
		await expect(page.getByTestId("automation-form-mode")).toBeVisible();
		const options = page
			.getByTestId("automation-form-mode")
			.locator("option");
		await expect(options).toHaveCount(1);
		await expect(options.first()).toHaveValue("spawn");

		expectCleanConsole(problems);
	});

	test("loop option is visible on coding binding", async ({ page, problems }) => {
		// Mock automations list to avoid 404 console error.
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();
		await expect(page.getByTestId("automation-form")).toBeVisible();

		// Mode selector for coding binding shows both spawn and loop.
		const options = page
			.getByTestId("automation-form-mode")
			.locator("option");
		await expect(options).toHaveCount(2);
		await expect(options.nth(0)).toHaveValue("spawn");
		await expect(options.nth(1)).toHaveAttribute("value", "loop");

		expectCleanConsole(problems);
	});

	test("loop form shows iteration cap and marker; spawn form shows interval and count", async ({
		page,
		problems,
	}) => {
		// Mock automations list to avoid 404 console error.
		await page.route("**/api/bindings/dotfiles/automations", (route) => {
			route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
		});
		await page.goto("/dotfiles/automations");
		await page.getByTestId("automation-create-btn").click();

		// Default mode is spawn — spawn fields visible, loop fields hidden.
		await expect(page.getByTestId("automation-form-interval")).toBeVisible();
		await expect(page.getByTestId("automation-form-count")).toBeVisible();
		await expect(
			page.getByTestId("automation-form-iter-cap"),
		).not.toBeVisible();
		await expect(
			page.getByTestId("automation-form-marker"),
		).not.toBeVisible();

		// Switch to loop.
		await page.getByTestId("automation-form-mode").selectOption("loop");
		await expect(page.getByTestId("automation-form-interval")).not.toBeVisible();
		await expect(page.getByTestId("automation-form-count")).not.toBeVisible();
		await expect(page.getByTestId("automation-form-iter-cap")).toBeVisible();
		await expect(page.getByTestId("automation-form-marker")).toBeVisible();

		expectCleanConsole(problems);
	});
});
