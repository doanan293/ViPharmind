import { HttpResponse, http } from "msw"
import { RouterContextProvider } from "react-router"
import { afterEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { NEXT_PATH_STORAGE_KEY } from "~/features/auth/lib/google"
import GoogleCallback, { clientLoader } from "~/routes/auth/google-callback"

import { worker } from "../../../tests/msw/browser"
import { TestProviders } from "../../../tests/utils/providers"

const CALLBACK_PATH = "/api/v1/auth/google/callback"
const PROBLEM_HEADERS = { "Content-Type": "application/problem+json" }
const HTTP_BAD_REQUEST = 400
const HTTP_FOUND = 302

/** Runs the client loader for a callback URL and returns the redirect it throws. */
async function redirectFrom(search: string): Promise<Response> {
  const url = new URL(`/auth/google/callback${search}`, window.location.origin)
  try {
    await clientLoader({
      request: new Request(url),
      params: {},
      context: new RouterContextProvider(),
      url,
      pattern: url.pathname,
      serverLoader: () => Promise.reject(new Error("no server loader")),
    })
  } catch (thrown) {
    if (thrown instanceof Response) {
      return thrown
    }
    throw thrown
  }
  throw new Error("the loader did not redirect")
}

describe("Google sign-in callback route", () => {
  afterEach(() => {
    window.sessionStorage.clear()
  })

  test("signs in and redirects to the page the user started from", async () => {
    let forwarded = ""
    worker.use(
      http.get(CALLBACK_PATH, ({ request }) => {
        forwarded = new URL(request.url).search
        return new HttpResponse(null, { status: 204 })
      })
    )
    window.sessionStorage.setItem(NEXT_PATH_STORAGE_KEY, "/collections")

    const response = await redirectFrom("?code=abc&state=xyz")

    expect(response.status).toBe(HTTP_FOUND)
    expect(response.headers.get("Location")).toBe("/collections")
    expect(new URLSearchParams(forwarded).get("code")).toBe("abc")
  })

  test("sends the user back to login with the error code Google sign-in failed with", async () => {
    worker.use(
      http.get(CALLBACK_PATH, () =>
        HttpResponse.json(
          { title: "Invalid state", code: "OAUTH_INVALID_STATE" },
          { status: HTTP_BAD_REQUEST, headers: PROBLEM_HEADERS }
        )
      )
    )

    const response = await redirectFrom("?code=abc&state=bad")

    expect(response.headers.get("Location")).toBe(
      "/login?error=OAUTH_INVALID_STATE"
    )
  })

  test("reports an unknown error when the request fails without a problem", async () => {
    worker.use(http.get(CALLBACK_PATH, () => HttpResponse.error()))

    const response = await redirectFrom("?code=abc&state=xyz")

    expect(response.headers.get("Location")).toBe("/login?error=UNKNOWN")
  })

  test("shows progress while the sign-in completes", async () => {
    await render(
      <TestProviders>
        <GoogleCallback />
      </TestProviders>
    )

    await expect
      .element(page.getByText("Đang hoàn tất đăng nhập Google…"))
      .toBeVisible()
  })
})
