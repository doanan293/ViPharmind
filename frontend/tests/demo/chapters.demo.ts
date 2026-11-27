import { test } from "@playwright/test"

import { account } from "./chapters/account"
import { admin } from "./chapters/admin"
import { auth } from "./chapters/auth"
import { chat } from "./chapters/chat"
import { collections } from "./chapters/collections"
import { history } from "./chapters/history"
import { intro } from "./chapters/intro"
import { orgs } from "./chapters/orgs"
import { publicPages } from "./chapters/public"
import { ask, type DemoContext } from "./support/demo"

/** Chapters that wait for real LLM answers can take many minutes. */
const LLM_CHAPTER_TIMEOUT_MS = 900_000

// Each chapter on its own while developing; prerequisites (accounts) run first in the same page.
test("intro", async ({ page }) => {
  await intro(page, {})
})

test("auth", async ({ page }) => {
  const ctx: DemoContext = {}
  await auth(page, ctx)
})

test("chat", async ({ page }) => {
  test.setTimeout(LLM_CHAPTER_TIMEOUT_MS)
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await chat(page, ctx)
})

test("history", async ({ page }) => {
  test.setTimeout(LLM_CHAPTER_TIMEOUT_MS)
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
  test.setTimeout(LLM_CHAPTER_TIMEOUT_MS)
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await orgs(page, ctx)
  await collections(page, ctx)
})

test("account", async ({ page }) => {
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await account(page, ctx)
})

test("admin", async ({ page }) => {
  const ctx: DemoContext = {}
  await auth(page, ctx)
  await admin(page, ctx)
})

test("public", async ({ page }) => {
  await publicPages(page, {})
})
