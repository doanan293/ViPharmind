import { writeFileSync } from "node:fs"

import { test } from "@playwright/test"

import { account } from "./chapters/account"
import { admin } from "./chapters/admin"
import { auth } from "./chapters/auth"
import { chat } from "./chapters/chat"
import { collections } from "./chapters/collections"
import { history } from "./chapters/history"
import { orgs } from "./chapters/orgs"
import { publicPages } from "./chapters/public"
import { intro } from "./chapters/intro"
import {
  chapterTitle,
  type DemoContext,
  logOut,
  recording,
  switchUser,
} from "./support/demo"

// The whole demo as one test, one page, so one continuous video.
test("walkthrough", async ({ page }) => {
  // The video starts with the page, just before the test body.
  recording.startedAt = Date.now()
  recording.waits = []
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
  await chapterTitle(page, "6. Cài đặt tài khoản")
  await switchUser(page, ctx.owner!)
  await account(page, ctx)
  await chapterTitle(page, "7. Quản trị")
  await admin(page, ctx)
  await page.goto("/chat")
  await logOut(page)
  await chapterTitle(page, "8. Trang công khai")
  await publicPages(page, ctx)
  writeFileSync(
    test.info().outputPath("waits.json"),
    JSON.stringify({ waits: recording.waits }, null, 2)
  )
})
