import { test } from "@playwright/test"

import { auth } from "./chapters/auth"
import { intro } from "./chapters/intro"
import type { DemoContext } from "./support/demo"

// Each chapter on its own while developing; prerequisites (accounts) run first in the same page.
test("intro", async ({ page }) => {
  await intro(page, {})
})

test("auth", async ({ page }) => {
  const ctx: DemoContext = {}
  await auth(page, ctx)
})
