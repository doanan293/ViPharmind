import { test } from "@playwright/test"

import { auth } from "./chapters/auth"
import { chat } from "./chapters/chat"
import { collections } from "./chapters/collections"
import { history } from "./chapters/history"
import { orgs } from "./chapters/orgs"
import { intro } from "./chapters/intro"
import { ask, type DemoContext } from "./support/demo"

// Each chapter on its own while developing; prerequisites (accounts) run first in the same page.
test("intro", async ({ page }) => {
  await intro(page, {})
})

test("auth", async ({ page }) => {
  const ctx: DemoContext = {}
  await auth(page, ctx)
})

test("chat", async ({ page }) => {
  test.setTimeout(900_000)
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await chat(page, ctx)
})

test("history", async ({ page }) => {
  test.setTimeout(900_000)
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await page.goto("/chat")
  await ask(page, "Paracetamol người lớn uống tối đa bao nhiêu một ngày?")
  await history(page, ctx)
})

test("orgs", async ({ page }) => {
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await orgs(page, ctx)
})

test("collections", async ({ page }) => {
  test.setTimeout(900_000)
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await orgs(page, ctx)
  await collections(page, ctx)
})
