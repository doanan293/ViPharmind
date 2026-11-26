import { type Page, expect } from "@playwright/test"

import {
  type DemoContext,
  caption,
  logIn,
  makeSuperadmin,
  switchUser,
} from "../support/demo"

/** Admin console: only a superadmin (granted on the server) sees it; locking a user ends their session. */
export async function admin(page: Page, ctx: DemoContext): Promise<void> {
  if (ctx.owner === undefined || ctx.outsider === undefined)
    throw new Error("run auth first")

  await caption(page, "Trang quản trị không tồn tại với người dùng thường")
  await switchUser(page, ctx.outsider)
  await page.goto("/admin")
  await expect(page.getByText("Không tìm thấy trang")).toBeVisible()

  await caption(
    page,
    "Quyền quản trị chỉ cấp được trên máy chủ, bằng dòng lệnh"
  )
  makeSuperadmin(ctx.owner.email)
  const browser = page.context().browser()
  if (browser === null) throw new Error("no browser")
  const guest = await browser.newContext({ locale: "vi-VN" })
  const guestPage = await guest.newPage()
  await logIn(guestPage, ctx.outsider)

  await page.goto("/chat")
  await switchUser(page, ctx.owner)
  await page.goto("/admin")
  await caption(page, "Quản trị viên tìm người dùng và khoá tài khoản")
  await page
    .getByRole("searchbox", { name: /Tìm theo tên/ })
    .fill(ctx.outsider.email)
  const row = page.getByRole("row", { name: new RegExp(ctx.outsider.email) })
  await expect(row).toBeVisible()
  await row.getByRole("button", { name: "Khoá" }).click()
  await page.getByRole("button", { name: "Xác nhận" }).click()
  await expect(row.getByText("Đã khoá", { exact: true })).toBeVisible()

  await caption(page, "Phiên của tài khoản bị khoá kết thúc ngay")
  await guestPage.goto("/chat")
  await expect(guestPage).toHaveURL(/\/login/)
  await guest.close()
  await page.waitForTimeout(1_500)
}
