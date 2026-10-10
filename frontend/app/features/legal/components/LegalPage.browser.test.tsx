import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"
import { createRoutesStub } from "react-router"

import { LegalPage } from "~/features/legal/components/LegalPage"

import { TestProviders } from "../../../../tests/utils/providers"

async function open(document: "privacy" | "terms", locale: "vi" | "en") {
  const Stub = createRoutesStub([
    {
      path: "/",
      Component: () => <LegalPage document={document} locale={locale} />,
    },
  ])
  await render(
    <TestProviders language={locale}>
      <Stub initialEntries={["/"]} />
    </TestProviders>
  )
}

describe("LegalPage", () => {
  test("the privacy policy says where data lives and that admins can read it", async () => {
    await open("privacy", "vi")
    await expect
      .element(
        page.getByRole("heading", {
          level: 1,
          name: "Chính sách quyền riêng tư",
        })
      )
      .toBeVisible()
    expect(document.title).toBe("Chính sách quyền riêng tư · ViPharMind")
    await expect.element(page.getByText(/Neon/).first()).toBeVisible()
    await expect.element(page.getByText(/Qdrant Cloud/).first()).toBeVisible()
    await expect.element(page.getByText(/DeepInfra/).first()).toBeVisible()
    await expect
      .element(page.getByText(/không được ghi vào nhật ký/).first())
      .toBeVisible()
    await expect
      .element(page.getByText(/thuộc về người dùng hoặc tổ chức/).first())
      .toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Điều khoản sử dụng" }))
      .toBeVisible()
  })

  test("the terms say answers do not replace a pharmacist, in English too", async () => {
    await open("terms", "en")
    await expect
      .element(page.getByRole("heading", { level: 1, name: "Terms of use" }))
      .toBeVisible()
    await expect
      .element(
        page
          .getByText(/do not replace advice from a pharmacist or doctor/)
          .first()
      )
      .toBeVisible()
    await expect
      .element(page.getByText(/may be disabled/).first())
      .toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Privacy policy" }))
      .toHaveAttribute("href", "/en/privacy")
  })
})
