import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["line"]],
  outputDir: "../quality/evidence/browser/test-results",
  use: {
    baseURL: process.env.LOCALFLOW_QA_URL,
    headless: true,
    viewport: { width: 1440, height: 960 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "edge-full", testMatch: "**/localflow.spec.js", use: { channel: "msedge" } },
    { name: "chromium-compat", testMatch: "**/compatibility.spec.js", use: { browserName: "chromium" } },
    { name: "chrome-compat", testMatch: "**/compatibility.spec.js", use: { browserName: "chromium", channel: "chrome" } },
    { name: "firefox-compat", testMatch: "**/compatibility.spec.js", use: { browserName: "firefox" } },
  ],
});
