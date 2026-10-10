import { expect, test } from "vitest"

import type { AccountView } from "~/api/gen/schemas"

import { accountLabel } from "./account-label"

const base: AccountView = {
  id: "0b7c3f5e-4a53-4f5e-9a51-7d1e2f3a4b5c",
  email: null,
  phone_number: "+84912345678",
  display_name: "",
  is_active: true,
  is_superuser: false,
  is_verified: true,
  email_verified: false,
  phone_verified: true,
  password_set: false,
  google_linked: false,
}

test("prefers the display name, then email, then phone", () => {
  expect(accountLabel({ ...base, display_name: "An" })).toBe("An")
  expect(accountLabel({ ...base, email: "an@example.com" })).toBe(
    "an@example.com"
  )
  expect(accountLabel(base)).toBe("+84912345678")
})
