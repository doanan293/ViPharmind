import { execFileSync } from "node:child_process"
import { randomUUID } from "node:crypto"
import path from "node:path"

import { type Page, expect } from "@playwright/test"

export type DemoUser = { email: string; name: string; password: string }

/**
 * Waits for an answer, in milliseconds since the recording started; `scripts/demo-video.py`
 * speeds these up in the final video. The walkthrough sets `recording.startedAt`.
 */
export const recording: {
  startedAt: number | null
  waits: [number, number][]
} = {
  startedAt: null,
  waits: [],
}

/** Accounts created by earlier chapters, reused by later ones. */
export type DemoContext = {
  owner?: DemoUser
  member?: DemoUser
  outsider?: DemoUser
}

const STACK = path.resolve(
  import.meta.dirname,
  "../../../../scripts/demo-stack.sh"
)

function uniqueEmail(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 6)}@vipharmind.demo`
}

export function demoUser(prefix: string, name: string): DemoUser {
  return {
    email: uniqueEmail(prefix),
    name,
    password: `demo-${randomUUID().slice(0, 8)}`,
  }
}

/** The newest one-time code the log email/SMS provider wrote for `to`. */
export async function latestCode(
  to: string,
  since: Date = new Date(0)
): Promise<string> {
  const pattern = new RegExp(
    `not sent to ${to.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}:[^\\n]*?(\\d{6})`,
    "g"
  )
  const deadline = Date.now() + 30_000
  while (Date.now() < deadline) {
    const logs = execFileSync(
      STACK,
      ["logs", "--since", since.toISOString(), "backend"],
      { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
    )
    const codes = [...logs.matchAll(pattern)].map((match) => match[1])
    const code = codes.at(-1)
    if (code !== undefined) return code
    await new Promise((resolve) => setTimeout(resolve, 1_000))
  }
  throw new Error(`no code for ${to} in the backend log`)
}

/** A caption strip at the bottom of the screen, so the video explains itself. */
export async function caption(
  page: Page,
  text: string,
  ms = 1_400
): Promise<void> {
  await page.evaluate(
    ({ label, duration }) => {
      const id = "demo-caption"
      document.getElementById(id)?.remove()
      const strip = document.createElement("div")
      strip.id = id
      strip.textContent = label
      Object.assign(strip.style, {
        position: "fixed",
        left: "50%",
        bottom: "32px",
        transform: "translateX(-50%)",
        zIndex: "2147483647",
        padding: "12px 24px",
        borderRadius: "12px",
        background: "rgba(15, 23, 42, 0.88)",
        color: "white",
        font: "500 20px/1.4 system-ui",
        maxWidth: "80vw",
        textAlign: "center",
        pointerEvents: "none",
      })
      document.body.appendChild(strip)
      setTimeout(() => strip.remove(), duration)
    },
    { label: text, duration: ms }
  )
  await page.waitForTimeout(ms)
}

/** A full-screen chapter title card. */
export async function chapterTitle(
  page: Page,
  title: string,
  ms = 1_500
): Promise<void> {
  await page.evaluate(
    ({ label, duration }) => {
      const card = document.createElement("div")
      card.textContent = label
      Object.assign(card.style, {
        position: "fixed",
        inset: "0",
        zIndex: "2147483647",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(15, 23, 42, 0.92)",
        color: "white",
        font: "600 44px/1.3 system-ui",
        pointerEvents: "none",
      })
      document.body.appendChild(card)
      setTimeout(() => card.remove(), duration)
    },
    { label: title, duration: ms }
  )
  await page.waitForTimeout(ms)
}

export async function signUp(page: Page, user: DemoUser): Promise<void> {
  const since = new Date()
  await page.goto("/register")
  await page.waitForLoadState("networkidle")
  await page.getByLabel("Tên hiển thị", { exact: true }).fill(user.name)
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(user.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "Tạo tài khoản" }).click()
  await expect(page.getByText(/Chúng tôi đã gửi mã 6 số tới/)).toBeVisible()
  await page.getByLabel("Mã xác minh").fill(await latestCode(user.email, since))
  await page.getByRole("button", { name: "Xác minh email" }).click()
  await expect(page).toHaveURL(/\/chat$/)
}

export async function logIn(page: Page, user: DemoUser): Promise<void> {
  await page.goto("/login")
  await page.waitForLoadState("networkidle")
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill(user.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page).toHaveURL(/\/chat$/)
}

export async function logOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Menu tài khoản" }).click()
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click()
  await expect(page).toHaveURL(/\/login(\?|$)/)
}

export async function switchUser(page: Page, user: DemoUser): Promise<void> {
  await logOut(page)
  await logIn(page, user)
}

/**
 * Sends a chat message and waits until the answer has finished streaming. A transient
 * failure of the LLM provider (an error notice with "Thử lại") is retried once, so one 429
 * does not cost the whole recording.
 */
export async function ask(page: Page, question: string): Promise<void> {
  const done = page.getByRole("button", { name: "Chưa hữu ích" })
  const retry = page.getByRole("button", { name: "Thử lại" })
  const before = await done.count()
  const retriesBefore = await retry.count()
  await page
    .getByRole("textbox", { name: "Tin nhắn", exact: true })
    .fill(question)
  await page.getByRole("button", { name: "Gửi" }).click()
  const waitStarted = Date.now()
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const answered = expect(done).toHaveCount(before + 1, { timeout: 180_000 })
    const failed = expect(retry).toHaveCount(retriesBefore + 1, {
      timeout: 180_000,
    })
    const outcome = await Promise.any([
      answered.then(() => "answered" as const),
      failed.then(() => "failed" as const),
    ])
    if (outcome === "answered") {
      if (recording.startedAt !== null) {
        recording.waits.push([
          waitStarted - recording.startedAt,
          Date.now() - recording.startedAt,
        ])
      }
      return
    }
    if (attempt === 0) await retry.last().click()
  }
  throw new Error(`the answer to "${question}" failed twice`)
}

/** The path of the newest invitation link emailed to `to` (log email provider). */
export async function latestInvitationPath(
  to: string,
  since: Date
): Promise<string> {
  const escaped = to.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const pattern = new RegExp(
    `not sent to ${escaped}:[^\\n]*?https?://[^\\s/]+(/invitations/[\\w-]+)`,
    "g"
  )
  const deadline = Date.now() + 30_000
  while (Date.now() < deadline) {
    const logs = execFileSync(
      STACK,
      ["logs", "--since", since.toISOString(), "backend"],
      {
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
      }
    )
    const found = [...logs.matchAll(pattern)].map((match) => match[1]).at(-1)
    if (found !== undefined) return found
    await new Promise((resolve) => setTimeout(resolve, 1_000))
  }
  throw new Error(`no invitation for ${to} in the backend log`)
}

/** Grants superadmin on the server, the only way the product allows (CLI). */
export function makeSuperadmin(email: string): void {
  execFileSync(
    STACK,
    ["exec", "backend", "pharma-agent", "superadmin", "grant", email],
    {
      encoding: "utf8",
    }
  )
}
