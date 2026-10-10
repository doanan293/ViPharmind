import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { Toaster } from "~/components/ui/toast"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"
import { PasswordForm } from "./PasswordForm"

async function renderForm(
  passwordSet = true,
  hasVerifiedEmail = true
): Promise<void> {
  await render(
    <TestProviders>
      <Toaster>
        <PasswordForm
          passwordSet={passwordSet}
          hasVerifiedEmail={hasVerifiedEmail}
        />
      </Toaster>
    </TestProviders>
  )
}

async function fillNewPasswords(value: string, confirm: string): Promise<void> {
  await page.getByLabelText("Mật khẩu mới", { exact: true }).fill(value)
  await page
    .getByLabelText("Nhập lại mật khẩu mới", { exact: true })
    .fill(confirm)
  await page.getByRole("button", { name: "Đổi mật khẩu" }).click()
}

function problem(code: string): Response {
  return HttpResponse.json(
    { title: "Bad request", status: 400, code },
    { status: 400, headers: { "Content-Type": "application/problem+json" } }
  )
}

describe("PasswordForm", () => {
  test("changes the password with the current one and clears the fields", async () => {
    const bodies: unknown[] = []
    worker.use(
      http.put("*/api/v1/account/password", async ({ request }) => {
        bodies.push(await request.json())
        return new HttpResponse(null, { status: 204 })
      })
    )
    await renderForm()

    await page
      .getByLabelText("Mật khẩu hiện tại", { exact: true })
      .fill("mat-khau-cu-123")
    await fillNewPasswords("mat-khau-moi-123", "mat-khau-moi-123")

    await expect.element(page.getByText("Đã đổi mật khẩu.")).toBeVisible()
    await expect
      .element(page.getByLabelText("Mật khẩu mới", { exact: true }))
      .toHaveValue("")
    expect(bodies).toEqual([
      { current_password: "mat-khau-cu-123", new_password: "mat-khau-moi-123" },
    ])
  })

  test("a phone account sets its first password without a current one", async () => {
    const bodies: unknown[] = []
    worker.use(
      http.put("*/api/v1/account/password", async ({ request }) => {
        bodies.push(await request.json())
        return new HttpResponse(null, { status: 204 })
      })
    )
    await renderForm(false)

    await expect
      .element(page.getByLabelText("Mật khẩu hiện tại", { exact: true }))
      .not.toBeInTheDocument()
    await fillNewPasswords("mat-khau-moi-123", "mat-khau-moi-123")

    await expect.element(page.getByText("Đã đổi mật khẩu.")).toBeVisible()
    expect(bodies).toEqual([
      { current_password: null, new_password: "mat-khau-moi-123" },
    ])
  })

  test("requires at least 8 characters without calling the API", async () => {
    await renderForm()

    await page
      .getByLabelText("Mật khẩu hiện tại", { exact: true })
      .fill("mat-khau-cu-123")
    await fillNewPasswords("1234567", "1234567")

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Mật khẩu tối thiểu 8 ký tự.")
  })

  test("reports a mismatch without calling the API", async () => {
    await renderForm()

    await page
      .getByLabelText("Mật khẩu hiện tại", { exact: true })
      .fill("mat-khau-cu-123")
    await fillNewPasswords("mat-khau-moi-123", "mat-khau-khac-123")

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Hai mật khẩu không khớp.")
  })

  test("asks for the current password before calling the API", async () => {
    await renderForm()

    await fillNewPasswords("mat-khau-moi-123", "mat-khau-moi-123")

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Nhập mật khẩu hiện tại.")
  })

  test("puts a wrong current password on its own field", async () => {
    worker.use(
      http.put("*/api/v1/account/password", () =>
        problem("CURRENT_PASSWORD_INVALID")
      )
    )
    await renderForm()

    await page
      .getByLabelText("Mật khẩu hiện tại", { exact: true })
      .fill("sai-mat-khau")
    await fillNewPasswords("mat-khau-moi-123", "mat-khau-moi-123")

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Mật khẩu hiện tại không đúng.")
  })

  test("puts the server password rule on the new password field", async () => {
    worker.use(
      http.put("*/api/v1/account/password", () => problem("PASSWORD_INVALID"))
    )
    await renderForm()

    await page
      .getByLabelText("Mật khẩu hiện tại", { exact: true })
      .fill("mat-khau-cu-123")
    await fillNewPasswords("mat-khau-moi-123", "mat-khau-moi-123")

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Mật khẩu cần từ 8 đến 128 ký tự.")
  })

  test("tells an account without a verified email when the password starts to work", async () => {
    await renderForm(false, false)
    await expect
      .element(
        page.getByText(
          "Mật khẩu dùng để đăng nhập bằng email, nên chỉ có tác dụng sau khi bạn thêm và xác minh email."
        )
      )
      .toBeVisible()
  })

  test("says nothing extra when the email is verified", async () => {
    await renderForm(false, true)
    await expect
      .element(page.getByText(/chỉ có tác dụng sau khi/))
      .not.toBeInTheDocument()
  })
})
