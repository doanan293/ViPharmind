import { afterEach, describe, expect, test, vi } from "vitest"

import { RouterContextProvider } from "react-router"

import { action, loader } from "./api-proxy"

type Forwarded = { url: string; init: RequestInit & { duplex?: string } }

function stubBackend(response: Response): Forwarded[] {
  const calls: Forwarded[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init })
      return Promise.resolve(response)
    })
  )
  return calls
}

function args(request: Request) {
  return {
    request,
    params: { "*": new URL(request.url).pathname.slice("/api/".length) },
    context: new RouterContextProvider(),
    url: new URL(request.url),
    pattern: "/api/*",
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe("api proxy", () => {
  test("forwards a GET with its cookie, without the host", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.example.run.app")
    const calls = stubBackend(Response.json({ status: "ok" }))
    const response = await loader(
      args(
        new Request("https://vipharmind.vercel.app/api/v1/health?x=1", {
          headers: {
            cookie: "pharma_session=abc",
            host: "vipharmind.vercel.app",
            "accept-encoding": "gzip",
          },
        })
      )
    )
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe("https://api.example.run.app/api/v1/health?x=1")
    const headers = new Headers(calls[0]?.init.headers)
    expect(headers.get("cookie")).toBe("pharma_session=abc")
    expect(headers.has("host")).toBe(false)
    expect(headers.get("accept-encoding")).toBe("identity")
    expect(headers.has("x-vipharmind-proxy")).toBe(false)
    expect(calls[0]?.init.redirect).toBe("manual")
    expect(await response.json()).toEqual({ status: "ok" })
  })

  test("forwards a POST body and its CSRF header, and keeps every set-cookie", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.example.run.app/")
    const upstream = new Response(null, { status: 204 })
    upstream.headers.append("set-cookie", "pharma_session=new; HttpOnly")
    upstream.headers.append("set-cookie", "csrftoken=t; Path=/")
    const calls = stubBackend(upstream)
    const response = await action(
      args(
        new Request("https://vipharmind.vercel.app/api/v1/auth/cookie/login", {
          method: "POST",
          headers: {
            "content-type": "application/x-www-form-urlencoded",
            "x-csrftoken": "t",
          },
          body: "username=a%40b.c&password=x",
        })
      )
    )
    expect(calls[0]?.url).toBe(
      "https://api.example.run.app/api/v1/auth/cookie/login"
    )
    expect(calls[0]?.init.method).toBe("POST")
    expect(new Headers(calls[0]?.init.headers).get("x-csrftoken")).toBe("t")
    expect(await new Response(calls[0]?.init.body).text()).toBe(
      "username=a%40b.c&password=x"
    )
    expect(response.status).toBe(204)
    expect(response.headers.getSetCookie()).toEqual([
      "pharma_session=new; HttpOnly",
      "csrftoken=t; Path=/",
    ])
  })
})

describe("api proxy identity", () => {
  test("proves it is our proxy with the shared secret and drops a forged one", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.example.run.app")
    vi.stubEnv("API_PROXY_SECRET", "s3cret")
    const calls = stubBackend(Response.json({}))
    await loader(
      args(
        new Request("https://vipharmind.vercel.app/api/v1/users/me", {
          headers: { "x-vipharmind-proxy": "forged" },
        })
      )
    )
    expect(new Headers(calls[0]?.init.headers).get("x-vipharmind-proxy")).toBe(
      "s3cret"
    )
  })

  test("drops encoding headers that no longer describe the decoded body", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.example.run.app")
    stubBackend(
      new Response("{}", {
        headers: {
          "content-type": "application/json",
          "content-encoding": "gzip",
          "content-length": "20",
        },
      })
    )
    const response = await loader(
      args(new Request("https://vipharmind.vercel.app/api/v1/health"))
    )
    expect(response.headers.has("content-encoding")).toBe(false)
    expect(response.headers.has("content-length")).toBe(false)
    expect(response.headers.get("content-type")).toBe("application/json")
  })
})
