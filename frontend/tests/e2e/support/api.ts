import { randomUUID } from "node:crypto"

import type {
  APIRequestContext,
  APIResponse,
  BrowserContext,
  Page,
} from "@playwright/test"
import { z } from "zod"

export const API = "/api/v1"

export type TestUser = { email: string; password: string; displayName: string }

const CodeResponse = z.object({ code: z.string().regex(/^\d{6}$/) })

const ConversationCreated = z.object({ id: z.string() })

async function assertStatus(
  response: APIResponse,
  expected: number
): Promise<void> {
  if (response.status() !== expected) {
    throw new Error(
      `${response.url()} returned ${response.status()}, expected ${expected}: ${await response.text()}`
    )
  }
}

/**
 * The CSRF header for an API context that already holds a session cookie (the backend only
 * checks unsafe requests that carry one), and nothing for a cookieless context.
 */
async function csrfFor(
  request: APIRequestContext
): Promise<Record<string, string>> {
  const cookie = (await request.storageState()).cookies.find(
    (item) => item.name === "csrftoken"
  )
  return cookie === undefined ? {} : { "x-csrftoken": cookie.value }
}

/** A fresh user per test (the password satisfies the 8-character minimum). */
export function newUser(): TestUser {
  const id = randomUUID().slice(0, 8)
  return {
    email: `e2e-${id}@example.com`,
    password: `e2e-mat-khau-${id}`,
    displayName: `E2E ${id}`,
  }
}

export async function registerUser(
  request: APIRequestContext,
  user: TestUser
): Promise<void> {
  const response = await request.post(`${API}/auth/register`, {
    headers: await csrfFor(request),
    data: {
      email: user.email,
      password: user.password,
      display_name: user.displayName,
    },
  })
  await assertStatus(response, 201)
  const verify = await request.post(`${API}/auth/email/verify`, {
    headers: await csrfFor(request),
    data: {
      email: user.email,
      code: await latestCode(request, user.email),
      password: user.password,
    },
  })
  await assertStatus(verify, 204)
}

/** The last code the E2E backend sent to an email address or E.164 number. */
export async function latestCode(
  request: APIRequestContext,
  to: string
): Promise<string> {
  const response = await request.get(`${API}/__e2e/outbox/code`, {
    params: { to },
  })
  await assertStatus(response, 200)
  return CodeResponse.parse(await response.json()).code
}

/**
 * Cookie login. Pass `page.request` so the browser context receives
 * `pharma_session`; the following `GET /users/me` makes the CSRF middleware
 * set `csrftoken`.
 */
export async function loginUser(
  request: APIRequestContext,
  user: TestUser
): Promise<void> {
  const login = await request.post(`${API}/auth/cookie/login`, {
    form: { username: user.email, password: user.password },
  })
  await assertStatus(login, 204)
  await assertStatus(await request.get(`${API}/users/me`), 200)
}

export async function csrfHeaders(
  context: BrowserContext
): Promise<Record<string, string>> {
  const cookie = (await context.cookies()).find(
    (item) => item.name === "csrftoken"
  )
  if (cookie === undefined) {
    throw new Error("csrftoken cookie is missing; call loginUser first")
  }
  return { "x-csrftoken": cookie.value }
}

export async function createConversation(page: Page): Promise<string> {
  const response = await page.request.post(`${API}/conversations`, {
    headers: await csrfHeaders(page.context()),
  })
  await assertStatus(response, 201)
  const body: unknown = await response.json()
  return ConversationCreated.parse(body).id
}

/** Runs one full turn through the real stream endpoint and waits for `[DONE]`. */
export async function askOverApi(
  page: Page,
  conversationId: string,
  message: string
): Promise<void> {
  const response = await page.request.post(`${API}/chat/stream`, {
    headers: await csrfHeaders(page.context()),
    data: { conversation_id: conversationId, message },
  })
  await assertStatus(response, 200)
  const body = await response.text()
  if (!body.includes("data: [DONE]")) {
    throw new Error(
      `stream for "${message}" did not finish: ${body.slice(-500)}`
    )
  }
}

const InvitationResponse = z.object({
  path: z.string().startsWith("/invitations/"),
})

/** What `pharma-agent superadmin grant <email>` does on a real server. */
export async function makeSuperadmin(
  request: APIRequestContext,
  email: string
): Promise<void> {
  const response = await request.post(`${API}/__e2e/superadmin`, {
    headers: await csrfFor(request),
    data: { email },
  })
  await assertStatus(response, 204)
}

/** The path of the last invitation link emailed to `email`, or null when none was sent. */
export async function latestInvitationPath(
  request: APIRequestContext,
  email: string
): Promise<string | null> {
  const response = await request.get(`${API}/__e2e/outbox/invitation`, {
    params: { to: email },
  })
  if (response.status() === 404) {
    return null
  }
  await assertStatus(response, 200)
  return InvitationResponse.parse(await response.json()).path
}
