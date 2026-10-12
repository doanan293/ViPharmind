import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { GoogleButton } from "~/features/auth/components/GoogleButton"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

function health(google: boolean) {
  return http.get("*/api/v1/health", () =>
    HttpResponse.json({
      status: "ok",
      agent: true,
      checks: {},
      reasons: {},
      phone_sign_in_enabled: true,
      google_sign_in_enabled: google,
    })
  )
}

async function renderButton() {
  await render(
    <TestProviders>
      <p>email-form</p>
      <GoogleButton nextPath="/" />
    </TestProviders>
  )
}

describe("GoogleButton", () => {
  test("offers Google after a separator when the server has a Google client", async () => {
    worker.use(health(true))
    await renderButton()
    await expect
      .element(page.getByRole("button", { name: "Tiếp tục với Google" }))
      .toBeVisible()
    await expect.element(page.getByText("hoặc")).toBeVisible()
  })

  test("renders nothing when Google sign-in is not configured", async () => {
    worker.use(health(false))
    await renderButton()
    await expect.element(page.getByText("email-form")).toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Tiếp tục với Google" }))
      .not.toBeInTheDocument()
    await expect.element(page.getByText("hoặc")).not.toBeInTheDocument()
  })
})
