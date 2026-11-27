import type { ReactNode } from "react"
import { renderToString } from "react-dom/server"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router"
import { describe, expect, test } from "vitest"

import {
  LegalConsent,
  LegalLinks,
} from "~/features/legal/components/LegalLinks"
import type { Language } from "~/i18n/config"

import { createTestI18n } from "../../../../tests/utils/i18n"

function renderIn(language: Language, element: ReactNode): string {
  return renderToString(
    <I18nextProvider i18n={createTestI18n(language)}>
      <MemoryRouter>{element}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("LegalLinks", () => {
  test("links both Vietnamese legal pages in a Vietnamese UI", () => {
    const html = renderIn("vi", <LegalLinks />)

    expect(html).toContain('href="/privacy"')
    expect(html).toContain("Chính sách quyền riêng tư")
    expect(html).toContain('href="/terms"')
    expect(html).toContain("Điều khoản sử dụng")
  })

  test("links the English pages in an English UI", () => {
    const html = renderIn("en", <LegalLinks />)

    expect(html).toContain('href="/en/privacy"')
    expect(html).toContain("Privacy policy")
    expect(html).toContain('href="/en/terms"')
  })
})

describe("LegalConsent", () => {
  test("asks the user to agree to the terms and the privacy policy", () => {
    const html = renderIn("en", <LegalConsent />)

    expect(html).toContain("By creating an account you agree to the ")
    expect(html).toContain('href="/en/terms"')
    expect(html).toContain('href="/en/privacy"')
  })

  test("reads in Vietnamese in a Vietnamese UI", () => {
    const html = renderIn("vi", <LegalConsent />)

    expect(html).toContain("Khi tạo tài khoản, bạn đồng ý với ")
    expect(html).toContain('href="/terms"')
  })
})
