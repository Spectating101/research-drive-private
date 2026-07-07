import { defineConfig } from "@playwright/test";

const baseURL = process.env.YZU_DESK_URL || "http://127.0.0.1:5179";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
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
