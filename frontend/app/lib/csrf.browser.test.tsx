import { afterEach, describe, expect, test } from "vitest"

import { CSRF_COOKIE, CSRF_HEADER, readCsrfToken } from "~/lib/csrf"

async function expireCookie(name: string): Promise<void> {
  await cookieStore.delete({ name, path: "/" })
}

describe("readCsrfToken", () => {
  afterEach(async () => {
    await expireCookie(CSRF_COOKIE)
    await expireCookie("theme")
  })

  test("returns undefined before the backend sets the cookie", () => {
    expect(readCsrfToken()).toBeUndefined()
  })

  test("reads csrftoken among other cookies", async () => {
    await cookieStore.set({ name: "theme", value: "dark", path: "/" })
    await cookieStore.set({ name: "csrftoken", value: "abc123", path: "/" })
    expect(readCsrfToken()).toBe("abc123")
  })

  test("matches the backend CSRF middleware names", () => {
    expect(CSRF_COOKIE).toBe("csrftoken")
    expect(CSRF_HEADER).toBe("x-csrftoken")
  })
})
