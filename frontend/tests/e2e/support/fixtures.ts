import { test as base, type Page } from "@playwright/test"

import { loginUser, newUser, registerUser, type TestUser } from "./api"

type Fixtures = {
  /** A registered user that no other test uses. */
  user: TestUser
  /** `page` with the user's session and CSRF cookies already set. */
  signedInPage: Page
}

export const test = base.extend<Fixtures>({
  user: async ({ request }, provide) => {
    const user = newUser()
    await registerUser(request, user)
    await provide(user)
  },
  signedInPage: async ({ page, user }, provide) => {
    await loginUser(page.request, user)
    await provide(page)
  },
})

export { expect } from "@playwright/test"
