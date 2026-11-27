import { HttpResponse, http } from "msw"
import { createRoutesStub } from "react-router"
import { afterEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { cleanup, render } from "vitest-browser-react"

import LoginPage from "~/routes/auth/login"
import RegisterPage from "~/routes/auth/register"

import { worker } from "../../../tests/msw/browser"
import { accountView } from "../../../tests/utils/account"
import { TestProviders } from "../../../tests/utils/providers"

const HTTP_UNAUTHORIZED = 401

function ChatRoute() {
  return <p>chat-page</p>
}

const Stub = createRoutesStub([
  { path: "/login", Component: LoginPage },
  { path: "/register", Component: RegisterPage },
  { path: "/chat", Component: ChatRoute },
])

function signedIn(isSignedIn: boolean) {
  return http.get("/api/v1/users/me", () =>
    isSignedIn
      ? HttpResponse.json(accountView())
      : HttpResponse.json(
          { title: "Unauthorized", code: "UNAUTHORIZED" },
          {
            status: HTTP_UNAUTHORIZED,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
  )
}

async function open(entry: string, isSignedIn = false) {
  worker.use(
    signedIn(isSignedIn),
    http.get("*/api/v1/health", () =>
      HttpResponse.json({
        status: "ok",
        agent: true,
        checks: {},
        reasons: {},
        phone_sign_in_enabled: true,
        google_sign_in_enabled: false,
      })
    )
  )
  await render(
    <TestProviders>
      <Stub initialEntries={[entry]} />
    </TestProviders>
  )
}

// Unmount before the MSW handlers reset, so the page's queries never hit a missing handler.
afterEach(async () => {
  await cleanup()
})

describe("login page", () => {
  test("shows the error a failed Google sign-in sent back", async () => {
    await open("/login?error=OAUTH_INVALID_STATE")

    await expect
      .element(
        page.getByText("Phiên đăng nhập Google không hợp lệ. Vui lòng thử lại.")
      )
      .toBeVisible()
  })

  test("shows a generic error for an error code it does not know", async () => {
    await open("/login?error=SOMETHING_ELSE")

    await expect
      .element(page.getByText("Đã xảy ra lỗi. Vui lòng thử lại."))
      .toBeVisible()
  })

  test("links to registration, keeping where the user was heading", async () => {
    await open("/login?next=%2Fchat")

    await expect
      .element(page.getByRole("link", { name: "Đăng ký" }))
      .toHaveAttribute("href", "/register?next=%2Fchat")
    await expect
      .element(page.getByRole("link", { name: "Quên mật khẩu?" }))
      .toBeVisible()
  })

  test("sends a signed-in user straight to the next page", async () => {
    await open("/login?next=%2Fchat", true)

    await expect.element(page.getByText("chat-page")).toBeVisible()
  })
})

describe("register page", () => {
  test("asks for consent to the legal pages and links back to login", async () => {
    await open("/register?next=%2Fchat")

    await expect
      .element(page.getByRole("heading", { name: "Tạo tài khoản" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Điều khoản sử dụng" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Đăng nhập" }))
      .toHaveAttribute("href", "/login?next=%2Fchat")
  })

  test("sends a signed-in user straight to the next page", async () => {
    await open("/register?next=%2Fchat", true)

    await expect.element(page.getByText("chat-page")).toBeVisible()
  })
})
