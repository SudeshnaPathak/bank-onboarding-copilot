import { defineConfig } from "@playwright/test";

// Expects `make backend` (port 8000) and `make frontend` (port 5173) to be running.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure" },
});
