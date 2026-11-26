import { defineConfig, devices } from "@playwright/test";
const webPort = process.env.E2E_WEB_PORT || "3000";
const apiPort = process.env.E2E_API_PORT || "8000";
export default defineConfig({
  testDir: "../../tests/e2e",
  fullyParallel: false,
  use: { baseURL: `http://localhost:${webPort}`, trace: "retain-on-failure" },
  projects: [
    {
      name: "desktop-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 900 },
      },
    },
    {
      name: "mobile-webkit",
      use: { ...devices["iPhone 13"], viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: [
    {
      command: `cd ../../backend && E2E_APP_ORIGIN=http://localhost:${webPort} .venv/bin/uvicorn tests.e2e_server:app --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      url: `http://127.0.0.1:${apiPort}/api/v1/session`,
      reuseExistingServer: false,
    },
    {
      command: `pnpm dev --port ${webPort}`,
      url: `http://localhost:${webPort}/login`,
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
});
