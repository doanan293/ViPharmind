import { type Page, expect } from "@playwright/test"

import { type DemoContext, caption, logIn, logOut } from "../support/demo"

/** Account settings: display name, password, sessions, language and theme. */
export async function account(page: Page, ctx: DemoContext): Promise<void> {
  if (ctx.owner === undefined) throw new Error("run auth first")
  await caption(
    page,
    "Cài đặt tài khoản: hồ sơ, mật khẩu, phiên đăng nhập, giao diện"
  )
  await page.getByRole("link", { name: "Cài đặt" }).click()
  await expect(page.getByRole("heading", { name: "Cài đặt" })).toBeVisible()

  await caption(page, "Đổi tên hiển thị")
  ctx.owner.name = "DS. Nguyễn Văn An"
  const name = page.getByLabel("Tên hiển thị")
  await name.fill(ctx.owner.name)
  await page.getByRole("button", { name: "Lưu", exact: true }).click()
  await expect(page.getByText("Đã lưu tên hiển thị.")).toBeVisible()

  await caption(
    page,
    "Phiên đăng nhập: thấy cả điện thoại vừa đăng nhập, đăng xuất từ xa"
  )
  const browser = page.context().browser()
  if (browser === null) throw new Error("no browser")
  const phone = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    locale: "vi-VN",
  })
  const phonePage = await phone.newPage()
  await logIn(phonePage, ctx.owner)
  await phone.close()
  await page.reload()
  await expect(page.getByText("Thiết bị này")).toBeVisible()
  await page
    .getByRole("button", { name: "Đăng xuất mọi thiết bị khác" })
    .click()
  await expect(
    page.getByRole("button", { name: "Đăng xuất mọi thiết bị khác" })
  ).toHaveCount(0)

  await caption(page, "Đổi mật khẩu: cần mật khẩu hiện tại")
  const newPassword = `${ctx.owner.password}-2`
  await page.getByLabel("Mật khẩu hiện tại").fill(ctx.owner.password)
  await page.getByLabel("Mật khẩu mới", { exact: true }).fill(newPassword)
  await page.getByLabel("Nhập lại mật khẩu mới").fill(newPassword)
  await page.getByRole("button", { name: "Đổi mật khẩu" }).click()
  await expect(page.getByText("Đã đổi mật khẩu.")).toBeVisible()
  ctx.owner.password = newPassword

  await caption(page, "Giao diện tối")
  await page.getByRole("radio", { name: "Tối" }).click()
  await expect(page.locator("html")).toHaveClass(/\bdark\b/)
  await page.getByRole("link", { name: "Trò chuyện", exact: true }).click()
  await page.waitForTimeout(800)
  await page.getByRole("link", { name: "Cài đặt" }).click()
  await page.getByRole("radio", { name: "Sáng" }).click()
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/)

  await caption(page, "Đăng nhập lại bằng mật khẩu mới")
  await logOut(page)
  await logIn(page, ctx.owner)
}
