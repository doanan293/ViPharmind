import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { SignInMethods } from "~/features/auth/components/SignInMethods"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

function health(phone: boolean) {
  return http.get("*/api/v1/health", () =>
    HttpResponse.json({
      status: "ok",
      agent: true,
      checks: {},
      reasons: {},
      phone_sign_in_enabled: phone,
    })
  )
}

async function renderMethods() {
  await render(
    <TestProviders>
      <SignInMethods email={<p>email-form</p>} phone={<p>phone-form</p>} />
    </TestProviders>
  )
}

describe("SignInMethods", () => {
  test("offers email and phone when SMS is on", async () => {
    worker.use(health(true))
    await renderMethods()
    await expect
      .element(page.getByRole("tab", { name: "Số điện thoại" }))
      .toBeVisible()
    await expect.element(page.getByText("email-form")).toBeVisible()
  })

  test("shows only the email form when SMS is off", async () => {
    worker.use(health(false))
    await renderMethods()
    await expect.element(page.getByText("email-form")).toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Số điện thoại" }))
      .not.toBeInTheDocument()
  })
})
