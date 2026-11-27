import { HttpResponse, http } from "msw"
import { RouterContextProvider } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import GoogleLinkCallback, {
  clientLoader,
} from "~/routes/auth/google-link-callback"

import { worker } from "../../../tests/msw/browser"
import { TestProviders } from "../../../tests/utils/providers"

const CALLBACK_PATH = "/api/v1/auth/google/associate/callback"
const PROBLEM_HEADERS = { "Content-Type": "application/problem+json" }
const HTTP_BAD_REQUEST = 400
const HTTP_FOUND = 302

/** Runs the client loader for a callback URL and returns the redirect it throws. */
async function redirectFrom(search: string): Promise<Response> {
  const url = new URL(
    `/auth/google/link-callback${search}`,
    window.location.origin
  )
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

describe("Google link callback route", () => {
  test("links the account and returns to the settings page", async () => {
    worker.use(http.get(CALLBACK_PATH, () => HttpResponse.json({})))

    const response = await redirectFrom("?code=abc&state=xyz")

    expect(response.status).toBe(HTTP_FOUND)
    expect(response.headers.get("Location")).toBe("/settings")
  })

  test("returns to settings with the error code linking failed with", async () => {
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
      "/settings?error=OAUTH_INVALID_STATE"
    )
  })

  test("reports an unknown error when the request fails without a problem", async () => {
    worker.use(http.get(CALLBACK_PATH, () => HttpResponse.error()))

    const response = await redirectFrom("?code=abc&state=xyz")

    expect(response.headers.get("Location")).toBe("/settings?error=UNKNOWN")
  })

  test("shows progress while the account is linked", async () => {
    await render(
      <TestProviders>
        <GoogleLinkCallback />
      </TestProviders>
    )

    await expect
      .element(page.getByText("Đang hoàn tất đăng nhập Google…"))
      .toBeVisible()
  })
})
