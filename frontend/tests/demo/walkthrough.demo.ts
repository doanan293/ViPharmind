import { test } from "@playwright/test"

import { auth } from "./chapters/auth"
import { chat } from "./chapters/chat"
import { intro } from "./chapters/intro"
import { chapterTitle, type DemoContext } from "./support/demo"

// The whole demo as one test, one page, so one continuous video.
test("walkthrough", async ({ page }) => {
  const ctx: DemoContext = {}
  await page.goto("/")
  await chapterTitle(page, "ViPharmind")
  await intro(page, ctx)
  await chapterTitle(page, "1. Tài khoản")
  await auth(page, ctx)
  await chapterTitle(page, "2. Hỏi đáp thuốc")
  await chat(page, ctx)
})
