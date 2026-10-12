import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { AccountView } from "~/api/gen/schemas"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"
import { AccountSection } from "./AccountSection"

async function renderSection(user: AccountView) {
  let sessionRequests = 0
  worker.use(
    http.get("*/api/v1/account/sessions", () => {
      sessionRequests += 1
      return HttpResponse.json([])
    })
  )
  await render(
    <TestProviders>
      <AccountSection user={user} />
    </TestProviders>
  )
  await expect.poll(() => sessionRequests).toBeGreaterThan(0)
}

describe("AccountSection", () => {
  test("hides Google linking when the server has no Google client", async () => {
    await renderSection(accountView({ google_sign_in_enabled: false }))
    await expect
      .element(page.getByRole("heading", { name: "Email" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("heading", { name: "Google" }))
      .not.toBeInTheDocument()
  })

  test("keeps a linked Google account visible so it can be removed", async () => {
    await renderSection(
      accountView({ google_sign_in_enabled: false, google_linked: true })
    )
    await expect
      .element(page.getByRole("button", { name: "Gỡ liên kết" }))
      .toBeVisible()
  })
})
