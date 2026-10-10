import type { Browser, Page } from "@playwright/test"

import {
  type TestUser,
  latestInvitationPath,
  loginUser,
  newUser,
  registerUser,
} from "./support/api"
import { expect, test } from "./support/fixtures"

async function createOrganization(page: Page, name: string): Promise<void> {
  await page.goto("/organizations")
  await page.getByLabel("Tên tổ chức").fill(name)
  await page.getByRole("button", { name: "Tạo", exact: true }).click()
  await expect(page.getByRole("heading", { name })).toBeVisible()
}

async function invite(page: Page, email: string, role: string): Promise<void> {
  await page.getByRole("tab", { name: "Lời mời" }).click()
  await page.getByLabel("Email người được mời").fill(email)
  await page.getByLabel("Vai trò", { exact: true }).selectOption(role)
  await page.getByRole("button", { name: "Mời", exact: true }).click()
}

/** A second browser session for another user. */
async function signedIn(browser: Browser, user: TestUser): Promise<Page> {
  const context = await browser.newContext({ locale: "vi-VN" })
  const page = await context.newPage()
  await loginUser(page.request, user)
  return page
}

/** Accepting opens the organization's page. */
async function accept(page: Page, path: string, organization: string) {
  await page.goto(path)
  await page.getByRole("button", { name: "Tham gia" }).click()
  await expect(page.getByRole("heading", { name: organization })).toBeVisible()
}

test("owner invites by email, invitee registers, accepts and sees the collection as a source", async ({
  signedInPage: owner,
  request,
  browser,
}) => {
  await createOrganization(owner, "Khoa Dược E2E")
  await owner.getByRole("tab", { name: "Bộ tài liệu" }).click()
  await owner.getByLabel("Tên bộ tài liệu").fill("Phác đồ khoa")
  await owner.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
  await owner.getByRole("link", { name: /Phác đồ khoa/ }).click()
  await owner.getByLabel("Ai được thấy").selectOption("organization")
  await expect(owner.getByLabel("Ai được thấy")).toHaveValue("organization")
  await owner.goBack()

  const invitee = newUser()
  await invite(owner, invitee.email, "member")
  await expect(owner.getByText("Đã gửi lời mời.")).toBeVisible()

  await registerUser(request, invitee)
  const path = await latestInvitationPath(request, invitee.email)
  expect(path).not.toBeNull()
  const page = await signedIn(browser, invitee)
  await accept(page, path ?? "", "Khoa Dược E2E")

  await page.goto("/chat")
  await page.getByRole("combobox", { name: "Nguồn" }).click()
  await expect(page.getByText("Khoa Dược E2E")).toBeVisible()
  await expect(page.getByRole("option", { name: "Phác đồ khoa" })).toBeVisible()
})

test("a member invite waits for owner approval before the email goes out", async ({
  signedInPage: owner,
  request,
  browser,
}) => {
  await createOrganization(owner, "Nhà thuốc E2E")
  const member = newUser()
  await registerUser(request, member)
  await invite(owner, member.email, "member")
  const memberPage = await signedIn(browser, member)
  await accept(
    memberPage,
    (await latestInvitationPath(request, member.email)) ?? "",
    "Nhà thuốc E2E"
  )

  const guest = newUser()
  await invite(memberPage, guest.email, "member")
  await expect(
    memberPage.getByText(
      "Lời mời đang chờ chủ sở hữu hoặc biên tập viên duyệt."
    )
  ).toBeVisible()
  expect(await latestInvitationPath(request, guest.email)).toBeNull()

  await owner.reload()
  await owner.getByRole("tab", { name: "Lời mời" }).click()
  await expect(owner.getByText("Chờ duyệt")).toBeVisible()
  await owner.getByRole("button", { name: "Duyệt" }).click()
  await expect
    .poll(() => latestInvitationPath(request, guest.email))
    .toMatch(/^\/invitations\//)
})
