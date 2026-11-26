import { type Page, expect } from "@playwright/test"

import {
  type DemoContext,
  caption,
  latestInvitationPath,
  switchUser,
} from "../support/demo"

export const ORGANIZATION = "Khoa Dược Bệnh viện A"

/** Organizations: create, invite by email, accept as the invitee, change a role, read the activity log. */
export async function orgs(page: Page, ctx: DemoContext): Promise<void> {
  if (ctx.owner === undefined || ctx.member === undefined)
    throw new Error("run auth first")

  await caption(page, "Tạo tổ chức cho khoa dược")
  await page.getByRole("link", { name: "Tổ chức" }).click()
  await page.getByLabel("Tên tổ chức").fill(ORGANIZATION)
  await page.getByRole("button", { name: "Tạo", exact: true }).click()
  await expect(page.getByRole("heading", { name: ORGANIZATION })).toBeVisible()

  await caption(page, "Mời đồng nghiệp qua email với vai trò thành viên")
  await page.getByRole("tab", { name: "Lời mời" }).click()
  await page.getByLabel("Email người được mời").fill(ctx.member.email)
  await page.getByLabel("Vai trò", { exact: true }).selectOption("member")
  const since = new Date()
  await page.getByRole("button", { name: "Mời", exact: true }).click()
  await expect(page.getByText("Đã gửi lời mời.")).toBeVisible()
  const invitation = await latestInvitationPath(ctx.member.email, since)

  await caption(page, "Đồng nghiệp mở liên kết trong email và tham gia")
  await switchUser(page, ctx.member)
  await page.goto(invitation)
  await page.getByRole("button", { name: "Tham gia" }).click()
  await expect(page.getByRole("heading", { name: ORGANIZATION })).toBeVisible()

  await caption(page, "Chủ sở hữu nâng đồng nghiệp lên biên tập viên")
  await switchUser(page, ctx.owner)
  await page.getByRole("link", { name: "Tổ chức" }).click()
  await page.getByRole("link", { name: ORGANIZATION }).click()
  await page.getByRole("tab", { name: "Thành viên" }).click()
  await page.getByLabel(`Vai trò của ${ctx.member.name}`).selectOption("editor")
  await expect(page.getByLabel(`Vai trò của ${ctx.member.name}`)).toHaveValue(
    "editor"
  )

  await caption(page, "Nhật ký ghi lại mọi thay đổi trong tổ chức")
  await page.getByRole("tab", { name: "Nhật ký" }).click()
  await expect(
    page.getByText(new RegExp(`đã đổi vai trò của ${ctx.member.name}`))
  ).toBeVisible()
  await page.waitForTimeout(2_000)
}
