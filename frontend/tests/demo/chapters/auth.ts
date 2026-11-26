import { type Page, expect } from "@playwright/test"

import {
  type DemoContext,
  caption,
  demoUser,
  latestCode,
  logIn,
  logOut,
  signUp,
} from "../support/demo"

/** Accounts: email sign-up with a code, wrong password, phone sign-in, forgot password. */
export async function auth(page: Page, ctx: DemoContext): Promise<void> {
  ctx.owner = demoUser("owner", "Dược sĩ An")
  ctx.member = demoUser("member", "Dược sĩ Lợi")
  ctx.outsider = demoUser("guest", "Khách Bảo")

  await caption(page, "Đăng ký bằng email: hệ thống gửi mã 6 số để xác minh")
  await signUp(page, ctx.member)
  await logOut(page)
  await signUp(page, ctx.outsider)
  await logOut(page)
  await signUp(page, ctx.owner)
  await logOut(page)

  await caption(page, "Sai mật khẩu thì báo lỗi ngay cạnh ô nhập")
  await page.waitForLoadState("networkidle")
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(ctx.owner.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill("sai-mat-khau")
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page.getByRole("alert")).toBeVisible()

  await caption(page, "Quên mật khẩu: nhận mã qua email rồi đặt mật khẩu mới")
  await page.getByRole("link", { name: "Quên mật khẩu?" }).click()
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(ctx.owner.email)
  const since = new Date()
  await page.getByRole("button", { name: "Gửi mã" }).click()
  await expect(page.getByLabel("Mã xác minh")).toBeVisible()
  await page
    .getByLabel("Mã xác minh")
    .fill(await latestCode(ctx.owner.email, since))
  ctx.owner.password = `${ctx.owner.password}-moi`
  await page
    .getByLabel("Mật khẩu mới", { exact: true })
    .fill(ctx.owner.password)
  await page.getByLabel("Nhập lại mật khẩu mới").fill(ctx.owner.password)
  await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
  await expect(page).toHaveURL(/\/login$/)

  await caption(page, "Đăng nhập bằng số điện thoại với mã SMS")
  const local = `09${String(Date.now()).slice(-8)}`
  await page.waitForLoadState("networkidle")
  await page.getByRole("tab", { name: "Số điện thoại" }).click()
  await page.getByRole("textbox", { name: "Số điện thoại" }).fill(local)
  const smsSince = new Date()
  await page.getByRole("button", { name: "Gửi mã" }).click()
  await expect(page.getByLabel("Mã xác minh")).toBeVisible()
  await page
    .getByLabel("Mã xác minh")
    .fill(await latestCode(`+84${local.slice(1)}`, smsSince))
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await logOut(page)

  await caption(page, "Đăng nhập lại bằng mật khẩu mới")
  await logIn(page, ctx.owner)
}
