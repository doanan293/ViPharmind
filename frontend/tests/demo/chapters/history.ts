import { expect, type Page } from "@playwright/test"

import { ask, caption, type DemoContext } from "../support/demo"

/** Conversation history: newest first, reopen, rename, delete. Expects at least one conversation. */
export async function history(page: Page, _ctx: DemoContext): Promise<void> {
  // Conversation links point at /chat/<id>; the "new conversation" link is plain /chat.
  const items = page.locator('a[href^="/chat/"]')

  await caption(
    page,
    "Mở cuộc trò chuyện mới; cuộc cũ vẫn nằm trong danh sách bên trái"
  )
  await page.getByRole("link", { name: "Cuộc trò chuyện mới" }).click()
  // Wait for the empty conversation before `ask` counts the answers on the page.
  await expect(page).toHaveURL(/\/chat$/)
  await expect(page.getByRole("button", { name: "Chưa hữu ích" })).toHaveCount(
    0
  )
  await ask(page, "Amoxicillin có dùng được cho người dị ứng penicillin không?")

  await caption(
    page,
    "Danh sách xếp cuộc mới nhất lên đầu; bấm để mở lại cuộc cũ"
  )
  await expect(items.first()).toContainText("Amoxicillin")
  await items.nth(1).click()
  await expect(
    page.getByRole("button", { name: "Chưa hữu ích" }).first()
  ).toBeVisible()

  await caption(page, "Đổi tên cuộc trò chuyện")
  await page.getByRole("button", { name: /^Thao tác với Amoxicillin/ }).click()
  await page.getByRole("menuitem", { name: "Đổi tên" }).click()
  await page.getByRole("dialog").getByLabel("Tên").fill("Tra cứu amoxicillin")
  await page.getByRole("dialog").getByRole("button", { name: "Lưu" }).click()
  await expect(items.first()).toContainText("Tra cứu amoxicillin")

  await caption(page, "Xoá cuộc trò chuyện không cần nữa")
  await page
    .getByRole("button", { name: /^Thao tác với Tra cứu amoxicillin/ })
    .click()
  await page.getByRole("menuitem", { name: "Xoá" }).click()
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Xoá" })
    .click()
  await expect(items.filter({ hasText: "Tra cứu amoxicillin" })).toHaveCount(0)
}
