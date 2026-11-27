import { randomUUID } from "node:crypto"

import type {
  APIRequestContext,
  APIResponse,
  BrowserContext,
  Page,
} from "@playwright/test"
import { z } from "zod"

import { HttpStatus } from "../../../app/api/http-status"

export const API = "/api/v1"

export type TestUser = { email: string; password: string; displayName: string }

/** Characters of a UUID kept for a unique, readable test id. */
const ID_LENGTH = 8
/** How much of an unfinished stream body an error shows. */
const BODY_TAIL_CHARS = 500

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
  const id = randomUUID().slice(0, ID_LENGTH)
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
  await assertStatus(response, HttpStatus.CREATED)
  const verify = await request.post(`${API}/auth/email/verify`, {
    headers: await csrfFor(request),
    data: {
      email: user.email,
      code: await latestCode(request, user.email),
      password: user.password,
    },
  })
  await assertStatus(verify, HttpStatus.NO_CONTENT)
}

/** The last code the E2E backend sent to an email address or E.164 number. */
export async function latestCode(
  request: APIRequestContext,
  to: string
): Promise<string> {
  const response = await request.get(`${API}/__e2e/outbox/code`, {
    params: { to },
  })
  await assertStatus(response, HttpStatus.OK)
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
  await assertStatus(login, HttpStatus.NO_CONTENT)
  await assertStatus(await request.get(`${API}/users/me`), HttpStatus.OK)
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
  await assertStatus(response, HttpStatus.CREATED)
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
  await assertStatus(response, HttpStatus.OK)
  const body = await response.text()
  if (!body.includes("data: [DONE]")) {
    throw new Error(
      `stream for "${message}" did not finish: ${body.slice(-BODY_TAIL_CHARS)}`
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
  await assertStatus(response, HttpStatus.NO_CONTENT)
}

/** The path of the last invitation link emailed to `email`, or null when none was sent. */
export async function latestInvitationPath(
  request: APIRequestContext,
  email: string
): Promise<string | null> {
  const response = await request.get(`${API}/__e2e/outbox/invitation`, {
    params: { to: email },
  })
  if (response.status() === HttpStatus.NOT_FOUND) {
    return null
  }
  await assertStatus(response, HttpStatus.OK)
  return InvitationResponse.parse(await response.json()).path
}
