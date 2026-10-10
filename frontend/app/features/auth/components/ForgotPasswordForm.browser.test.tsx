import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { ForgotPasswordForm } from "~/features/auth/components/ForgotPasswordForm"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const Stub = createRoutesStub([
  { path: "/forgot-password", Component: ForgotPasswordForm },
  { path: "/login", Component: () => <p>login-page</p> },
])

describe("ForgotPasswordForm", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("requests a code, then resets the password and returns to login", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/auth/password/forgot", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      }),
      http.post("/api/v1/auth/password/reset", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 204 })
      })
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/forgot-password"]} />
      </TestProviders>
    )
    await page.getByLabelText("Email").fill("an@example.com")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page
      .getByLabelText("Mật khẩu mới", { exact: true })
      .fill("mat-khau-moi")
    await page.getByLabelText("Nhập lại mật khẩu mới").fill("mat-khau-moi")
    await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
    await expect.element(page.getByText("login-page")).toBeVisible()
    expect(bodies).toEqual([
      '{"email":"an@example.com"}',
      '{"email":"an@example.com","code":"123456","password":"mat-khau-moi"}',
    ])
  })

  test("the two passwords must match", async () => {
    worker.use(
      http.post(
        "/api/v1/auth/password/forgot",
        () => new HttpResponse(null, { status: 202 })
      )
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/forgot-password"]} />
      </TestProviders>
    )
    await page.getByLabelText("Email").fill("an@example.com")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page
      .getByLabelText("Mật khẩu mới", { exact: true })
      .fill("mat-khau-moi")
    await page.getByLabelText("Nhập lại mật khẩu mới").fill("khac-hoan-toan")
    await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
    await expect
      .element(page.getByText("Hai mật khẩu không khớp."))
      .toBeVisible()
  })
})
