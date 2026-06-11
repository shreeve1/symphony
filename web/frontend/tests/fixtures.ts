import { execFileSync } from "node:child_process";
import path from "node:path";
import { test as base, expect, type ConsoleMessage } from "@playwright/test";

// Collected browser-side problems for one page: console.error lines, uncaught
// exceptions (pageerror), and failed network requests. Specs read this and
// assert it's empty after the page has settled.
export interface PageProblems {
	errors: string[];
}

// console noise that is not a real app fault. Extend per-test via
// expectCleanConsole(problems, { ignore: [/.../] }) rather than widening this.
const DEFAULT_IGNORE: RegExp[] = [
	/favicon\.ico/i, // Next dev serves no favicon; browser logs a 404 for it
	/\?_rsc=/, // App Router RSC prefetch: aborts on supersede + dev cold-compile 500s
];

export const test = base.extend<{ problems: PageProblems }>({
	problems: [
		async ({ page }, use) => {
			const errors: string[] = [];

			page.on("console", (msg: ConsoleMessage) => {
				if (msg.type() === "error") {
					errors.push(`console.error: ${msg.text()}`);
				}
			});
			page.on("pageerror", (err) => {
				errors.push(`pageerror: ${err.message}`);
			});
			page.on("requestfailed", (req) => {
				const failure = req.failure()?.errorText ?? "unknown";
				errors.push(`requestfailed: ${req.method()} ${req.url()} (${failure})`);
			});
			page.on("response", (res) => {
				if (res.status() >= 400) {
					errors.push(
						`httperror: ${res.status()} ${res.request().method()} ${res.url()}`,
					);
				}
			});

			await use({ errors });
		},
		{ auto: true },
	],
});

export { expect };

const E2E_DB_PATH = path.resolve(__dirname, "../test-results/podium-e2e.db");

export function seedSkills(skills: { name: string; description?: string }[]) {
	const script = `
from web.api.db import connect
from web.cli.podium_skills import ensure_schema
skills = ${JSON.stringify(skills)}
with connect() as connection:
    ensure_schema(connection)
    connection.executemany(
        "INSERT INTO skill(name, description, source) VALUES (?, ?, 'e2e') "
        "ON CONFLICT(name) DO UPDATE SET description = excluded.description, source = excluded.source",
        [(skill["name"], skill.get("description", "")) for skill in skills],
    )
    connection.commit()
`;
	execFileSync("uv", ["run", "python", "-c", script], {
		cwd: path.resolve(__dirname, "../../.."),
		env: { ...process.env, PODIUM_DB_PATH: E2E_DB_PATH },
		stdio: "pipe",
	});
}

export function expectCleanConsole(
	problems: PageProblems,
	options: { ignore?: RegExp[] } = {},
) {
	const ignore = [...DEFAULT_IGNORE, ...(options.ignore ?? [])];
	const real = problems.errors.filter(
		(line) => !ignore.some((rx) => rx.test(line)),
	);
	expect(
		real,
		`unexpected browser console problems:\n${real.join("\n")}`,
	).toEqual([]);
}
