import { test } from "@playwright/test"

import { intro } from "./chapters/intro"
import { chapterTitle, type DemoContext } from "./support/demo"

// The whole demo as one test, one page, so one continuous video.
test("walkthrough", async ({ page }) => {
  const ctx: DemoContext = {}
  await page.goto("/")
  await chapterTitle(page, "ViPharmind")
  await intro(page, ctx)
})
