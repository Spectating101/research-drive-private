import { defineConfig } from "@playwright/test";

const baseURL = process.env.YZU_DESK_URL || "http://127.0.0.1:5179";
const devPort = new URL(baseURL).port || "5179";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  webServer: {
    command: `npm run dev -- --port ${devPort}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  use: {
    baseURL,
    headless: true,
    launchOptions: {
      args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
    },
    navigationTimeout: 45_000,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
