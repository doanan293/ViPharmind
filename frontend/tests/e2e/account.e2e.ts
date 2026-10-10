import { latestCode, newUser, registerUser } from "./support/api"
import { expect, test } from "./support/fixtures"

test("forgot password resets with an emailed code", async ({
  page,
  request,
}) => {
  const user = newUser()
  await registerUser(request, user)

  await page.goto("/login")
  await page.getByRole("link", { name: "Quên mật khẩu?" }).click()
  await expect(page).toHaveURL(/\/forgot-password$/)
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(user.email)
  await page.getByRole("button", { name: "Gửi mã" }).click()
  await page
    .getByLabel("Mã xác minh")
    .fill(await latestCode(request, user.email))
  await page
    .getByLabel("Mật khẩu mới", { exact: true })
    .fill("e2e-mat-khau-moi")
  await page.getByLabel("Nhập lại mật khẩu mới").fill("e2e-mat-khau-moi")
  await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
  await expect(page).toHaveURL(/\/login$/)

  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(user.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill("e2e-mat-khau-moi")
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page).toHaveURL(/\/chat$/)
})

test("phone sign-in creates an account and opens the chat", async ({
  page,
  request,
}) => {
  const local = `09${String(Date.now()).slice(-8)}`
  const e164 = `+84${local.slice(1)}`

  await page.goto("/login")
  await page.getByRole("tab", { name: "Số điện thoại" }).click()
  await page.getByRole("textbox", { name: "Số điện thoại" }).fill(local)
  await page.getByRole("button", { name: "Gửi mã" }).click()
  await page.getByLabel("Mã xác minh").fill(await latestCode(request, e164))
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page).toHaveURL(/\/chat$/)
})
