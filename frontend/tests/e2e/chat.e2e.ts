import type { Locator, Page, Request, Response } from "@playwright/test"
import { z } from "zod"

import { HttpStatus } from "../../app/api/http-status"
import { API, askOverApi, createConversation } from "./support/api"
import { expect, test } from "./support/fixtures"

/** Sixteen turns asked over the API take a few minutes against the stub LLM. */
const LONG_THREAD_TIMEOUT_MS = 180_000
/** 16 turns = 32 messages; the first page holds the newest 30 (turns 2–16). */
const LONG_THREAD_TURNS = 16
/** A wheel delta far larger than the thread, so it scrolls all the way to the top. */
const SCROLL_TO_TOP_DELTA = -20_000

const MessagePage = z.object({
  items: z.array(
    z.object({
      id: z.string(),
      role: z.string(),
      metadata: z
        .object({
          feedback: z
            .object({ rating: z.string(), note: z.string().nullish() })
            .nullish(),
        })
        .nullish(),
    })
  ),
  next_cursor: z.string().nullable(),
})

/** Records every "Đang …" text that appears in the page from now on, however briefly. */
async function recordPhases(page: Page): Promise<void> {
  await page.evaluate(() => {
    const seen: string[] = []
    Reflect.set(window, "e2ePhases", seen)
    const record = (text: string): void => {
      for (const match of text.matchAll(/Đang [^\n]+/g)) {
        if (!seen.includes(match[0])) {
          seen.push(match[0])
        }
      }
    }
    new MutationObserver(() => {
      // Each phase label is one i18n string, so it is one text node.
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT
      )
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        record(node.textContent ?? "")
      }
    }).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    })
  })
}

async function recordedPhases(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const value: unknown = Reflect.get(window, "e2ePhases")
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : []
  })
}

async function topOf(locator: Locator): Promise<number> {
  const box = await locator.boundingBox()
  if (box === null) {
    throw new Error("element is not rendered")
  }
  return box.y
}

function isFeedbackPost(response: Response): boolean {
  return (
    response.request().method() === "POST" &&
    /\/messages\/[^/]+\/feedback$/.test(new URL(response.url()).pathname)
  )
}

test("ask, see the phase, read the [1] answer, preview and open the full source", async ({
  signedInPage: page,
}) => {
  await page.goto("/chat")
  await recordPhases(page)

  await page
    .getByRole("textbox", { name: "Tin nhắn", exact: true })
    .fill("Liều paracetamol cho người lớn là bao nhiêu?")
  await page.getByRole("button", { name: "Gửi" }).click()

  await expect(page).toHaveURL(/\/chat\/[^/?#]+$/)
  const marker = page.getByRole("button", { name: "1", exact: true }).last()
  await expect(marker).toBeVisible()
  expect(await recordedPhases(page)).toContainEqual(
    expect.stringMatching(/^Đang tìm kiếm/)
  )

  await marker.hover()
  await expect(page.getByText(/^Trích từ mục /)).toBeVisible()

  const detail = page.waitForResponse((response) =>
    /\/messages\/[^/]+\/citations\/1$/.test(new URL(response.url()).pathname)
  )
  await marker.click()
  expect((await detail).status()).toBe(HttpStatus.OK)
  await expect(page.getByRole("heading", { name: "Nguồn [1]" })).toBeVisible()
  await expect(
    page.getByRole("region", { name: "Đoạn được trích dẫn" })
  ).toBeVisible()
})

test("👎 with a reason and a note is stored for the answer", async ({
  signedInPage: page,
}) => {
  const conversationId = await createConversation(page)
  await askOverApi(page, conversationId, "Paracetamol dùng cho trẻ em thế nào?")
  await page.goto(`/chat/${conversationId}`)

  const down = page.getByRole("button", { name: "Chưa hữu ích" }).last()
  await expect(down).toBeVisible()
  const answer = page
    .locator("[data-message-id]")
    .filter({ has: page.getByRole("button", { name: "Chưa hữu ích" }) })
    .last()
  const messageId = await answer.getAttribute("data-message-id")
  if (messageId === null) {
    throw new Error("the answer has no data-message-id")
  }

  const vote = page.waitForResponse(isFeedbackPost)
  await down.click()
  expect((await vote).ok()).toBe(true)

  const dialog = page.getByRole("dialog")
  await dialog.getByRole("button", { name: "Thiếu thông tin" }).click()
  await dialog
    .getByRole("textbox", { name: "Ghi chú" })
    .fill("Thiếu liều theo cân nặng")
  const details = page.waitForResponse(isFeedbackPost)
  await dialog.getByRole("button", { name: "Gửi phản hồi" }).click()
  expect((await details).ok()).toBe(true)
  await expect(dialog.getByText("Cảm ơn bạn đã góp ý.")).toBeVisible()

  const response = await page.request.get(
    `${API}/conversations/${conversationId}/messages`
  )
  expect(response.status()).toBe(HttpStatus.OK)
  const body: unknown = await response.json()
  const stored = MessagePage.parse(body).items.find(
    (item) => item.id === messageId
  )
  expect(stored?.metadata?.feedback).toMatchObject({
    rating: "down",
    note: "[Thiếu thông tin] Thiếu liều theo cân nặng",
  })

  await page.reload()
  await expect(
    page
      .locator(`[data-message-id="${messageId}"]`)
      .getByRole("button", { name: "Chưa hữu ích" })
  ).toHaveAttribute("aria-pressed", "true")
})

test("scrolling to the top loads older messages and keeps the reading position", async ({
  signedInPage: page,
}) => {
  test.setTimeout(LONG_THREAD_TIMEOUT_MS)
  const conversationId = await createConversation(page)
  for (let turn = 1; turn <= LONG_THREAD_TURNS; turn += 1) {
    await askOverApi(page, conversationId, `Câu hỏi số ${turn}`)
  }

  const messagesPath = `${API}/conversations/${conversationId}/messages`
  const isOlderPage = (url: URL): boolean =>
    url.pathname === messagesPath && url.searchParams.has("cursor")
  let release: () => void = () => undefined
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(isOlderPage, async (route) => {
    await held
    await route.continue()
  })

  await page.goto(`/chat/${conversationId}`)
  const thread = page.locator("[data-message-id]")
  await expect(thread.getByText("Câu hỏi số 16", { exact: true })).toBeVisible()
  await expect(thread.getByText("Câu hỏi số 1", { exact: true })).toHaveCount(0)

  const anchor = thread.getByText("Câu hỏi số 2", { exact: true })
  const olderRequest = page.waitForRequest((request: Request) =>
    isOlderPage(new URL(request.url()))
  )
  await anchor.hover()
  await page.mouse.wheel(0, SCROLL_TO_TOP_DELTA)
  await olderRequest
  await expect(anchor).toBeInViewport()
  const before = await topOf(anchor)

  release()

  await expect(thread.getByText("Câu hỏi số 1", { exact: true })).toHaveCount(1)
  await expect(anchor).toBeInViewport()
  expect(Math.abs((await topOf(anchor)) - before)).toBeLessThanOrEqual(2)
})
