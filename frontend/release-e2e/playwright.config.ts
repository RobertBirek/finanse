import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  retries: 0,
  timeout: 110_000,
  use: { baseURL: "http://127.0.0.1:5178", serviceWorkers: "block" },
});
