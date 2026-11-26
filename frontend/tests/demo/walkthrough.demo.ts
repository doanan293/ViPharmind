import { test } from "@playwright/test"

import { auth } from "./chapters/auth"
import { chat } from "./chapters/chat"
import { collections } from "./chapters/collections"
import { history } from "./chapters/history"
import { orgs } from "./chapters/orgs"
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
  await chapterTitle(page, "3. Lịch sử hội thoại")
  await history(page, ctx)
  await chapterTitle(page, "4. Tổ chức và phân quyền")
  await orgs(page, ctx)
  await chapterTitle(page, "5. Bộ tài liệu có phân quyền")
  await collections(page, ctx)
})
