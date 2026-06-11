import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// Two isolated web servers for e2e. Use non-dev ports plus a throwaway DB so
// specs never reuse or mutate an operator's live Podium process/database.
const E2E_API_PORT = 18090;
const E2E_WEB_PORT = 18091;
const E2E_API_ORIGIN = `http://127.0.0.1:${E2E_API_PORT}`;
const E2E_WEB_ORIGIN = `http://127.0.0.1:${E2E_WEB_PORT}`;
const E2E_DB_PATH = path.resolve(__dirname, "test-results/podium-e2e.db");

export default defineConfig({
	testDir: "./tests",
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: "list",
	use: {
		baseURL: E2E_WEB_ORIGIN,
		trace: "on-first-retry",
	},
	projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
	webServer: [
		{
			command:
				`mkdir -p test-results && rm -f ${E2E_DB_PATH} && ` +
				`PODIUM_DB_PATH=${E2E_DB_PATH} ` +
				`uv run uvicorn main:app --host 127.0.0.1 --port ${E2E_API_PORT} --app-dir ../api`,
			url: `${E2E_API_ORIGIN}/api/health`,
			reuseExistingServer: false,
			timeout: 120_000,
		},
		{
			command:
				`PODIUM_API_ORIGIN=${E2E_API_ORIGIN} ` +
				`NEXT_PUBLIC_PODIUM_API_ORIGIN=${E2E_API_ORIGIN} ` +
				`pnpm exec next dev -H 127.0.0.1 -p ${E2E_WEB_PORT}`,
			url: E2E_WEB_ORIGIN,
			reuseExistingServer: false,
			timeout: 120_000,
		},
	],
});
