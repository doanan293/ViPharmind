import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { PhoneLoginForm } from "~/features/auth/components/PhoneLoginForm"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const Stub = createRoutesStub([
  { path: "/login", Component: () => <PhoneLoginForm nextPath="/chat" /> },
  { path: "/chat", Component: () => <p>chat-page</p> },
  {
    path: "/register",
    Component: () => <PhoneLoginForm nextPath="/chat" intent="register" />,
  },
])

describe("PhoneLoginForm", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("sends the E.164 number, then signs in with the code", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/auth/phone/request", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      }),
      http.post("/api/v1/auth/phone/login", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 204 })
      })
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/login"]} />
      </TestProviders>
    )
    await page.getByLabelText("Số điện thoại").fill("0912 345 678")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByRole("button", { name: "Đăng nhập" }).click()
    await expect.element(page.getByText("chat-page")).toBeVisible()
    expect(bodies).toEqual([
      '{"phone":"+84912345678"}',
      '{"phone":"+84912345678","code":"123456"}',
    ])
  })

  test("an invalid number never reaches the server", async () => {
    await render(
      <TestProviders>
        <Stub initialEntries={["/login"]} />
      </TestProviders>
    )
    await page.getByLabelText("Số điện thoại").fill("12345")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await expect
      .element(page.getByText("Số điện thoại không hợp lệ."))
      .toBeVisible()
  })

  test("on the register page the code step continues instead of signing in", async () => {
    worker.use(
      http.post(
        "/api/v1/auth/phone/request",
        () => new HttpResponse(null, { status: 202 })
      )
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/register"]} />
      </TestProviders>
    )
    await page.getByLabelText("Số điện thoại").fill("0912 345 678")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await expect
      .element(page.getByRole("button", { name: "Tiếp tục" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Đăng nhập" }))
      .not.toBeInTheDocument()
  })
})
