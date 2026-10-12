import type { AccountView } from "~/api/gen/schemas"

/** A signed-in account with every field set; override what a test cares about. */
export function accountView(overrides: Partial<AccountView> = {}): AccountView {
  return {
    id: "0b8f7a52-5d4e-4c7b-9a51-3f7d1c2b9e10",
    email: "an@example.com",
    phone_number: null,
    display_name: "",
    is_active: true,
    is_superadmin: false,
    memberships: [],
    phone_sign_in_enabled: true,
    google_sign_in_enabled: true,
    is_verified: true,
    email_verified: true,
    phone_verified: false,
    password_set: true,
    google_linked: false,
    ...overrides,
  }
}
