import type { Page } from "@playwright/test"

import { type TestUser, latestCode, newUser } from "./support/api"
import { expect, test } from "./support/fixtures"

async function logIn(page: Page, user: TestUser): Promise<void> {
  // The form renders again once hydration and the session check settle; typing earlier
  // can be wiped.
  await page.waitForLoadState("networkidle")
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(user.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "Đăng nhập" }).click()
}

async function logOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Menu tài khoản" }).click()
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click()
  await expect(page).toHaveURL(/\/login(\?|$)/)
}

test("register, verify the email, log out, log in and log out again", async ({
  page,
  request,
}) => {
  const user = newUser()

  await page.goto("/register")
  await page.waitForLoadState("networkidle")
  await page.getByLabel("Tên hiển thị", { exact: true }).fill(user.displayName)
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(user.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "Tạo tài khoản" }).click()
  await expect(page.getByText(/Chúng tôi đã gửi mã 6 số tới/)).toBeVisible()
  await page
    .getByLabel("Mã xác minh")
    .fill(await latestCode(request, user.email))
  await page.getByRole("button", { name: "Xác minh email" }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await logOut(page)

  await logIn(page, user)
  await expect(page).toHaveURL(/\/chat$/)
  await logOut(page)

  await page.goto("/settings")
  await expect(page).toHaveURL(/\/login\?next=/)
})

test("an expired session returns to login and then back to the page", async ({
  signedInPage: page,
  user,
}) => {
  await page.goto("/chat")
  await expect(
    page.getByRole("textbox", { name: "Tin nhắn", exact: true })
  ).toBeVisible()

  // The browser no longer has a valid session, exactly as after the lifetime ends.
  await page.context().clearCookies({ name: "pharma_session" })
  await page.getByRole("link", { name: "Cài đặt", exact: true }).click()

  await expect(page).toHaveURL(/\/login\?next=(%2F|\/)settings/)
  await logIn(page, user)
  await expect(page).toHaveURL(/\/settings$/)
})
