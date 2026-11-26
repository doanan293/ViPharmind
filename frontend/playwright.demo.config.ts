import { defineConfig, devices } from "@playwright/test"

// The demo walkthrough against the local demo stack (scripts/demo-stack.sh up). Chapters run
// one by one while developing (`npm run demo -- -g <chapter>`); `npm run demo:video` records the
// whole walkthrough as one video in demo-videos/.
const video = process.env.DEMO_VIDEO === "1"

export default defineConfig({
  testDir: "./tests/demo",
  testMatch: video ? "walkthrough.demo.ts" : "**/*.demo.ts",
  outputDir: "./demo-videos",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: video ? 3_600_000 : 300_000,
  expect: { timeout: 120_000 },
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.DEMO_URL ?? "http://localhost:8080",
    viewport: { width: 1440, height: 900 },
    locale: "vi-VN",
    video: video ? { mode: "on", size: { width: 1440, height: 900 } } : "off",
    screenshot: "only-on-failure",
    launchOptions: { slowMo: 150 },
  },
})
