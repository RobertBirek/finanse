import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 2,
  timeout: 30000,
  outputDir: process.env.E2E_OUTPUT_DIR ?? "test-results",
  reporter: [
    ["list"],
    [
      "html",
      {
        outputFolder: process.env.E2E_REPORT_DIR ?? "playwright-report",
        open: "never",
      },
    ],
  ],
  use: {
    browserName: "chromium",
    baseURL: "https://ui.test.invalid",
    timezoneId: "Europe/Warsaw",
    locale: "pl-PL",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
    // No web server or real API: fixtures serve the exact production build in-memory.
    serviceWorkers: "block",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    {
      name: "mobile",
      use: {
        viewport: { width: 375, height: 850 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});
