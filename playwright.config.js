import { defineConfig } from "@playwright/test";

const baseURL = process.env.YZU_DESK_URL || "http://127.0.0.1:5179";
const devPort = new URL(baseURL).port || "5179";

export default defineConfig({
  testDir: "e2e",
  testIgnore: ["**/ui-contract.spec.js"],
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["list"], ["json", { outputFile: "docs/status/generated/yzu_desk_e2e.json" }]],
  webServer: {
    command: `npm run dev -- --port ${devPort}`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
  },
  use: {
    baseURL,
    headless: true,
    launchOptions: {
      headless: true,
      args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
    },
    navigationTimeout: 45_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
