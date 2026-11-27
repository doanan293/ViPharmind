import { RouterContextProvider } from "react-router"
import { afterEach, describe, expect, test, vi } from "vitest"

import { i18nextMiddleware } from "~/i18n/middleware.server"
import { loader as landingLoader } from "~/routes/public/landing"
import { loader as privacyLoader } from "~/routes/public/privacy"
import { loader as termsLoader } from "~/routes/public/terms"

const SITE = "https://pharma.example"
const LOCAL_SITE = "http://localhost:8080"

interface LoaderArgs {
  request: Request
  context: RouterContextProvider
  params: Record<string, never>
  url: URL
  pattern: string
}

/** Runs the real i18n middleware for `url`, then the route loader inside it. */
async function loadThrough<T>(
  url: string,
  loader: (args: LoaderArgs) => T
): Promise<T> {
  const args: LoaderArgs = {
    request: new Request(url),
    context: new RouterContextProvider(),
    params: {},
    url: new URL(url),
    pattern: new URL(url).pathname,
  }
  let data: T | undefined
  await i18nextMiddleware(args, () => {
    data = loader(args)
    return Promise.resolve(new Response())
  })
  if (data === undefined) {
    throw new Error("the middleware did not call the loader")
  }
  return data
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe("public page loaders", () => {
  test("the English landing page loads its title and description in English", async () => {
    vi.stubEnv("PUBLIC_SITE_URL", SITE)

    const data = await loadThrough(`${SITE}/en/`, landingLoader)

    expect(data.locale).toBe("en")
    expect(data.siteUrl).toBe(SITE)
    expect(data.title).toContain("ViPharmind")
    expect(data.description).toMatch(/drug|medicine/i)
  })

  test("the Vietnamese privacy page loads in Vietnamese on the public site", async () => {
    vi.stubEnv("PUBLIC_SITE_URL", SITE)

    const data = await loadThrough(`${SITE}/privacy`, privacyLoader)

    expect(data).toEqual({ locale: "vi", siteUrl: SITE })
  })

  test("the English terms page falls back to the local site URL when none is set", async () => {
    vi.stubEnv("PUBLIC_SITE_URL", undefined)

    const data = await loadThrough(`${LOCAL_SITE}/en/terms`, termsLoader)

    expect(data).toEqual({ locale: "en", siteUrl: LOCAL_SITE })
  })
})
