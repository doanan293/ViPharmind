import { QueryClient } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { Toaster } from "~/components/ui/toast"
import { ContactChangeFlow } from "~/features/settings/components/ContactChangeFlow"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ACCOUNT = {
  id: "0b7c3f5e-4a53-4f5e-9a51-7d1e2f3a4b5c",
  email: "an.moi@example.com",
  phone_number: null,
  display_name: "An",
  is_active: true,
  is_superadmin: false,
  memberships: [],
  phone_sign_in_enabled: true,
  is_verified: true,
  email_verified: true,
  phone_verified: false,
  password_set: true,
  google_linked: false,
}

describe("ContactChangeFlow", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("changes the email with a code sent to the new address", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/account/email", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      }),
      http.post("/api/v1/account/email/confirm", async ({ request }) => {
        bodies.push(await request.text())
        return HttpResponse.json(ACCOUNT)
      })
    )
    const client = new QueryClient()
    await render(
      <TestProviders client={client}>
        <Toaster>
          <ContactChangeFlow kind="email" current="an@example.com" verified />
        </Toaster>
      </TestProviders>
    )
    await page.getByRole("button", { name: "Đổi email" }).click()
    await page.getByLabelText("Email mới").fill("an.moi@example.com")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByRole("button", { name: "Xác nhận" }).click()
    await expect.element(page.getByText("Đã cập nhật email.")).toBeVisible()
    expect(bodies).toEqual([
      '{"email":"an.moi@example.com"}',
      '{"email":"an.moi@example.com","code":"123456"}',
    ])
    expect(client.getQueryData(["/api/v1/users/me"])).toEqual(ACCOUNT)
  })

  test("adds a phone number, sending E.164", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/account/phone", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      })
    )
    await render(
      <TestProviders>
        <ContactChangeFlow kind="phone" current={null} verified={false} />
      </TestProviders>
    )
    await page.getByRole("button", { name: "Thêm số điện thoại" }).click()
    await page.getByLabelText("Số điện thoại mới").fill("0912 345 678")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await expect.element(page.getByLabelText("Mã xác minh")).toBeVisible()
    expect(bodies).toEqual(['{"phone":"+84912345678"}'])
  })
})
