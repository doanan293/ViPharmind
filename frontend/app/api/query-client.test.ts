import { afterEach, describe, expect, test, vi } from "vitest"

import { ApiError } from "~/api/problem"
import { createQueryClient, queryClient, shouldRetry } from "~/api/query-client"

function unauthorized(): ApiError {
  return new ApiError({
    status: 401,
    code: "UNAUTHORIZED",
    title: "Unauthorized",
  })
}

describe("shouldRetry", () => {
  test("never retries client errors", () => {
    const notFound = new ApiError({
      status: 404,
      code: "CONVERSATION_NOT_FOUND",
      title: "Conversation not found",
    })
    expect(shouldRetry(0, notFound)).toBe(false)
    expect(shouldRetry(0, unauthorized())).toBe(false)
  })

  test("retries server and network errors at most twice", () => {
    const unavailable = new ApiError({
      status: 503,
      code: "AGENT_UNAVAILABLE",
      title: "Agent unavailable",
    })
    expect(shouldRetry(0, unavailable)).toBe(true)
    expect(shouldRetry(1, new TypeError("Failed to fetch"))).toBe(true)
    expect(shouldRetry(2, new TypeError("Failed to fetch"))).toBe(false)
  })
})

describe("createQueryClient", () => {
  test("reports a 401 from a query", async () => {
    const onUnauthorized = vi.fn<() => void>()
    const client = createQueryClient({ onUnauthorized })

    await expect(
      client.fetchQuery({
        queryKey: ["/api/v1/users/me"],
        queryFn: () => Promise.reject(unauthorized()),
      })
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  test("leaves a 401 alone when the query handles it itself", async () => {
    const onUnauthorized = vi.fn<() => void>()
    const client = createQueryClient({ onUnauthorized })

    await expect(
      client.fetchQuery({
        queryKey: ["/api/v1/users/me"],
        queryFn: () => Promise.reject(unauthorized()),
        meta: { skipAuthRedirect: true },
      })
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  test("reports a 401 from a mutation", async () => {
    const onUnauthorized = vi.fn<() => void>()
    const client = createQueryClient({ onUnauthorized })
    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => Promise.reject(unauthorized()),
    })

    await expect(mutation.execute(undefined)).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  test("ignores errors other than 401", async () => {
    const onUnauthorized = vi.fn<() => void>()
    const client = createQueryClient({ onUnauthorized })

    await expect(
      client.fetchQuery({
        queryKey: ["/api/v1/settings"],
        queryFn: () =>
          Promise.reject(
            new ApiError({
              status: 403,
              code: "CSRF_FAILED",
              title: "Forbidden",
            })
          ),
      })
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe("the app's query client", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /** Puts the tab on `path` and returns the spy that records navigations. */
  function openPage(pathname: string, search = "") {
    const assign = vi.fn<(url: string) => void>()
    vi.stubGlobal("window", { location: { pathname, search, assign } })
    return assign
  }

  test("sends the user to login after a 401, remembering the page", async () => {
    const assign = openPage("/chat", "?q=1")

    await expect(
      queryClient.fetchQuery({
        queryKey: ["redirect-test", "chat"],
        queryFn: () => Promise.reject(unauthorized()),
      })
    ).rejects.toBeInstanceOf(ApiError)

    expect(assign).toHaveBeenCalledExactlyOnceWith(
      "/login?next=%2Fchat%3Fq%3D1"
    )
  })

  test("stays put after a 401 on the login and register pages", async () => {
    for (const pathname of ["/login", "/register"]) {
      const assign = openPage(pathname)

      await expect(
        queryClient.fetchQuery({
          queryKey: ["redirect-test", pathname],
          queryFn: () => Promise.reject(unauthorized()),
        })
      ).rejects.toBeInstanceOf(ApiError)

      expect(assign).not.toHaveBeenCalled()
    }
  })
})
