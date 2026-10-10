import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, test } from "vitest"

import { fetcher } from "~/api/fetcher"

import { worker } from "../../tests/msw/browser"

describe("fetcher in the browser", () => {
  afterEach(() => {
    document.cookie = "csrftoken=; path=/; max-age=0"
  })

  test("calls the same origin and sends the CSRF token on unsafe methods", async () => {
    document.cookie = "csrftoken=token-123; path=/"
    worker.use(
      http.post("/api/v1/conversations", ({ request }) =>
        HttpResponse.json(
          { url: request.url, csrf: request.headers.get("x-csrftoken") },
          { status: 201 }
        )
      )
    )

    const body = await fetcher<{ url: string; csrf: string | null }>(
      "/api/v1/conversations",
      { method: "POST" }
    )

    expect(body).toEqual({
      url: `${window.location.origin}/api/v1/conversations`,
      csrf: "token-123",
    })
  })

  test("does not send the CSRF token on safe methods", async () => {
    document.cookie = "csrftoken=token-123; path=/"
    worker.use(
      http.get("/api/v1/users/me", ({ request }) =>
        HttpResponse.json({ csrf: request.headers.get("x-csrftoken") })
      )
    )

    await expect(fetcher("/api/v1/users/me")).resolves.toEqual({ csrf: null })
  })

  test("sends the UI language so emails and SMS match it", async () => {
    let language: string | null = null
    worker.use(
      http.get("/api/v1/probe", ({ request }) => {
        language = request.headers.get("accept-language")
        return HttpResponse.json({})
      })
    )
    document.documentElement.lang = "en"
    await fetcher("/api/v1/probe")
    expect(language).toBe("en")
  })
})
