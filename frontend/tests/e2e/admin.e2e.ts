import { loginUser, makeSuperadmin, newUser, registerUser } from "./support/api"
import { expect, test } from "./support/fixtures"

test("a superadmin disables a user, whose session ends", async ({
  signedInPage: admin,
  user,
  request,
  browser,
}) => {
  await makeSuperadmin(request, user.email)

  const victim = newUser()
  await registerUser(request, victim)
  const context = await browser.newContext({ locale: "vi-VN" })
  const victimPage = await context.newPage()
  await loginUser(victimPage.request, victim)
  await victimPage.goto("/chat")
  await expect(
    victimPage.getByRole("textbox", { name: "Tin nhắn" })
  ).toBeVisible()

  await admin.goto("/admin")
  await admin
    .getByRole("searchbox", { name: /Tìm theo tên/ })
    .fill(victim.email)
  const row = admin.getByRole("row", { name: new RegExp(victim.email) })
  await expect(row).toBeVisible()
  await row.getByRole("button", { name: "Khoá" }).click()
  await admin.getByRole("button", { name: "Xác nhận" }).click()
  await expect(row.getByText("Đã khoá", { exact: true })).toBeVisible()

  await victimPage.goto("/chat")
  await expect(victimPage).toHaveURL(/\/login/)
})

test("the console is a 404 for everyone else", async ({
  signedInPage: page,
}) => {
  await page.goto("/admin")
  await expect(page.getByText("Không tìm thấy trang")).toBeVisible()
})
