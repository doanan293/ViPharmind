import { type Page, expect } from "@playwright/test"

import {
  type DemoContext,
  caption,
  demoUser,
  signUp,
  switchUser,
} from "../support/demo"

/** Creates the owner and member accounts later chapters use. */
export async function accounts(page: Page, ctx: DemoContext): Promise<void> {
  ctx.owner = demoUser("owner", "Dược sĩ An")
  ctx.member = demoUser("member", "Dược sĩ Lợi")
  await caption(page, "Đăng ký tài khoản bằng email, xác minh bằng mã 6 số")
  await signUp(page, ctx.member)
  await page.getByRole("button", { name: "Menu tài khoản" }).click()
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click()
  await signUp(page, ctx.owner)
  await switchUser(page, ctx.member)
  await switchUser(page, ctx.owner)
  await expect(page.getByText(ctx.owner.name)).toBeVisible()
}
