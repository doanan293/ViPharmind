import { HttpResponse, http } from "msw"
import { describe, expect, test, vi } from "vitest"

import { getOauthAssociateGoogleAuthorizeMockHandler } from "~/api/gen/endpoints.msw"
import {
  completeGoogleLink,
  startGoogleLink,
} from "~/features/settings/lib/google-link"

import { worker } from "../../../../tests/msw/browser"

const CALLBACK_PATH = "/api/v1/auth/google/associate/callback"
const HTTP_BAD_REQUEST = 400

describe("Google account linking", () => {
  test("start opens the authorization URL the server returns", async () => {
    worker.use(
      getOauthAssociateGoogleAuthorizeMockHandler({
        authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?s=1",
      })
    )
    const assign = vi.fn<(url: string) => void>()

    await startGoogleLink(assign)

    expect(assign).toHaveBeenCalledExactlyOnceWith(
      "https://accounts.google.com/o/oauth2/v2/auth?s=1"
    )
  })

  test("complete forwards the code and state Google sent back", async () => {
    let search = ""
    worker.use(
      http.get(CALLBACK_PATH, ({ request }) => {
        search = new URL(request.url).search
        return HttpResponse.json({})
      })
    )

    await completeGoogleLink(
      new URL("http://localhost/auth/google/link-callback?code=c1&state=s1")
    )

    const params = new URLSearchParams(search)
    expect(params.get("code")).toBe("c1")
    expect(params.get("state")).toBe("s1")
  })

  test("complete rejects with the problem code when the server refuses", async () => {
    worker.use(
      http.get(CALLBACK_PATH, () =>
        HttpResponse.json(
          { title: "Taken", code: "OAUTH_USER_ALREADY_EXISTS" },
          {
            status: HTTP_BAD_REQUEST,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )

    await expect(
      completeGoogleLink(new URL("http://localhost/cb?code=c&state=s"))
    ).rejects.toHaveProperty("code", "OAUTH_USER_ALREADY_EXISTS")
  })
})
