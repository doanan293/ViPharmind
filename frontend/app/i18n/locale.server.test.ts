import { describe, expect, test } from "vitest"

import { HttpStatus } from "~/api/http-status"
import { localeCookie, setLocale } from "~/i18n/locale.server"

function localeRequest(locale: string): Request {
  return new Request("http://localhost/actions/locale", {
    method: "POST",
    body: new URLSearchParams({ locale }),
  })
}

describe("setLocale", () => {
  test("stores a supported language in the lng cookie", async () => {
    const response = await setLocale(localeRequest("en"))

    expect(response.status).toBe(HttpStatus.OK)
    const setCookie = response.headers.get("Set-Cookie")
    expect(setCookie).toContain("lng=")
    expect(await localeCookie.parse(setCookie)).toBe("en")
  })

  test("rejects an unsupported language and sets no cookie", async () => {
    const response = await setLocale(localeRequest("fr"))

    expect(response.status).toBe(HttpStatus.BAD_REQUEST)
    expect(response.headers.get("Set-Cookie")).toBeNull()
  })
})
