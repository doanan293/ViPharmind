import { expect, type Page } from "@playwright/test"

import { caption, type DemoContext, PAUSE_MS } from "../support/demo"

/** Public pages: landing in Vietnamese and English, privacy policy. */
/** The closing caption stays a little longer than the others. */
const CLOSING_CAPTION_MS = 2_000

export async function publicPages(
  page: Page,
  _ctx: DemoContext
): Promise<void> {
  await page.goto("/")
  await caption(page, "Trang giới thiệu công khai, tiếng Việt và tiếng Anh")
  await page
    .getByRole("heading", { name: "Tính năng" })
    .scrollIntoViewIfNeeded()
  await page.waitForTimeout(PAUSE_MS)
  await page.getByRole("link", { name: "English" }).click()
  await expect(page.locator("html")).toHaveAttribute("lang", "en")
  await page.waitForTimeout(PAUSE_MS)
  await caption(
    page,
    "Chính sách quyền riêng tư nêu rõ dữ liệu nào được lưu và ai được đọc"
  )
  await page.getByRole("link", { name: "Privacy policy" }).click()
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await page.waitForTimeout(PAUSE_MS)
  await page.goto("/")
  await caption(
    page,
    "ViPharmind: tra cứu thuốc có trích dẫn nguồn",
    CLOSING_CAPTION_MS
  )
}
