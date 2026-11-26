import { test } from "@playwright/test"

import { accounts } from "./chapters/accounts"
import { intro } from "./chapters/intro"
import type { DemoContext } from "./support/demo"

// Each chapter on its own while developing; prerequisites (accounts) run first in the same page.
test("intro", async ({ page }) => {
  await intro(page, {})
})

test("accounts", async ({ page }) => {
  const ctx: DemoContext = {}
  await accounts(page, ctx)
})
