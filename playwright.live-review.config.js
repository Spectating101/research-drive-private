import { defineConfig } from "@playwright/test";

const baseURL = process.env.YZU_DESK_URL || "https://previous.easycamp.tech";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "artifacts/live-review/report", open: "never" }],
  ],
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    navigationTimeout: 45_000,
    actionTimeout: 20_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    serviceWorkers: "block",
    launchOptions: {
      args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
    },
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
