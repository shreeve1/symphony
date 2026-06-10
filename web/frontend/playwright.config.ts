import { defineConfig, devices } from "@playwright/test";

// Two web servers for CI: the FastAPI backend on 8090 and Next on 8091.
// uvicorn runs via `uv run` so it resolves the repo's Python env; --app-dir
// points at web/api so `main:app` imports. The backend seeds podium.db from
// bindings.yml on first boot, giving the spec real `homelab` + `trading` rows.
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8091",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command:
        "uv run uvicorn main:app --host 127.0.0.1 --port 8090 --app-dir ../api",
      url: "http://127.0.0.1:8090/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "pnpm dev",
      url: "http://127.0.0.1:8091",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
