import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { RegisterForm } from "~/features/auth/components/RegisterForm"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

function RegisterRoute() {
  return <RegisterForm nextPath="/chat" />
}

function ChatRoute() {
  return <p>chat-page</p>
}

const Stub = createRoutesStub([
  { path: "/register", Component: RegisterRoute },
  { path: "/chat", Component: ChatRoute },
])

async function renderAndSubmit(password = "correct horse") {
  await render(
    <TestProviders>
      <Stub initialEntries={["/register"]} />
    </TestProviders>
  )
  await page.getByLabelText("Tên hiển thị").fill("An")
  await page.getByLabelText("Email").fill("an@example.com")
  await page.getByLabelText("Mật khẩu").fill(password)
  await page.getByRole("button", { name: "Tạo tài khoản" }).click()
}

describe("RegisterForm", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("registers, then verifies the email with the code and opens the next path", async () => {
    let registered: unknown = null
    let verifyBody = ""
    worker.use(
      http.post("/api/v1/auth/register", async ({ request }) => {
        registered = await request.json()
        return HttpResponse.json(
          { id: "u1", email: "an@example.com", display_name: "An" },
          { status: 201 }
        )
      }),
      // Registration already sent a code, so asking again lands in the cooldown.
      http.post("/api/v1/auth/email/verify/request", () =>
        HttpResponse.json(
          { code: "RATE_LIMITED", title: "Too Many Requests", status: 429 },
          {
            status: 429,
            headers: {
              "Content-Type": "application/problem+json",
              "Retry-After": "58",
            },
          }
        )
      ),
      http.post("/api/v1/auth/email/verify", async ({ request }) => {
        verifyBody = await request.text()
        return new HttpResponse(null, { status: 204 })
      }),
      http.get("/api/v1/users/me", () =>
        HttpResponse.json({ id: "u1", email: "an@example.com" })
      )
    )

    await renderAndSubmit()

    await expect
      .element(page.getByText(/Chúng tôi đã gửi mã 6 số tới an@example\.com/))
      .toBeVisible()
    await expect
      .element(page.getByRole("button", { name: /Gửi lại sau 5\d giây/ }))
      .toBeDisabled()
    await expect.element(page.getByRole("alert")).not.toBeInTheDocument()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByRole("button", { name: "Xác minh email" }).click()
    await expect.element(page.getByText("chat-page")).toBeVisible()
    expect(registered).toEqual({
      email: "an@example.com",
      password: "correct horse",
      display_name: "An",
    })
    // The password proves this is the person who registered, not just the inbox owner.
    expect(JSON.parse(verifyBody)).toEqual({
      email: "an@example.com",
      code: "123456",
      password: "correct horse",
    })
  })

  test("a code that could not be sent shows why and allows a resend at once", async () => {
    worker.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { id: "u1", email: "an@example.com", display_name: "An" },
          { status: 201 }
        )
      ),
      http.post("/api/v1/auth/email/verify/request", () =>
        HttpResponse.json(
          {
            code: "DELIVERY_FAILED",
            title: "Service Unavailable",
            status: 503,
          },
          {
            status: 503,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )

    await renderAndSubmit()

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Chưa gửi được mã. Vui lòng thử lại.")
    await expect
      .element(page.getByRole("button", { name: "Gửi lại mã" }))
      .toBeEnabled()
  })

  test("requires a password of at least 8 characters before calling the API", async () => {
    // No handler is registered: MSW's onUnhandledRequest "error" fails the test if a request is sent.
    await renderAndSubmit("1234567")

    await expect
      .element(page.getByText("Mật khẩu cần ít nhất 8 ký tự."))
      .toBeVisible()
  })

  test("shows the translated message when the email is taken", async () => {
    worker.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: "urn:pharma-agent:problem:register-user-already-exists",
            title: "User already exists",
            status: 400,
            code: "REGISTER_USER_ALREADY_EXISTS",
          },
          {
            status: 400,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )

    await renderAndSubmit()

    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent(
        "Email này đã được đăng ký. Nếu là của bạn, hãy dùng Quên mật khẩu."
      )
  })
})
