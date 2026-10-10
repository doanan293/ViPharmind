import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"
import { GoogleSetting } from "./GoogleSetting"

describe("GoogleSetting", () => {
  test("asks before removing Google and does nothing on cancel", async () => {
    let unlinked = 0
    worker.use(
      http.delete("/api/v1/account/oauth/google", () => {
        unlinked += 1
        return HttpResponse.json(accountView({ google_linked: false }))
      })
    )
    await render(
      <TestProviders>
        <GoogleSetting linked />
      </TestProviders>
    )

    await page.getByRole("button", { name: "Gỡ liên kết" }).click()
    await expect
      .element(
        page
          .getByRole("alertdialog")
          .getByText(/Bạn sẽ không thể đăng nhập bằng Google nữa\./)
      )
      .toBeVisible()
    await page.getByRole("button", { name: "Huỷ" }).click()
    await expect.element(page.getByRole("alertdialog")).not.toBeInTheDocument()
    expect(unlinked).toBe(0)

    await page.getByRole("button", { name: "Gỡ liên kết" }).click()
    await page.getByRole("button", { name: "Gỡ liên kết Google" }).click()
    await expect.poll(() => unlinked).toBe(1)
  })
})
