import { describe, expect, test } from "vitest"

import { legalMeta } from "~/features/legal/lib/meta"

const SITE = "https://pharma.example"

describe("legalMeta", () => {
  test("points the English privacy policy's canonical link at /en/privacy", () => {
    const tags = legalMeta("privacy", "en", SITE)

    expect(tags).toEqual(
      expect.arrayContaining([
        { name: "description", content: expect.any(String) },
        { tagName: "link", rel: "canonical", href: `${SITE}/en/privacy` },
      ])
    )
  })

  test("lists both languages and makes Vietnamese the default", () => {
    const tags = legalMeta("terms", "vi", SITE)

    expect(tags).toEqual(
      expect.arrayContaining([
        { tagName: "link", rel: "canonical", href: `${SITE}/terms` },
        {
          tagName: "link",
          rel: "alternate",
          hrefLang: "vi",
          href: `${SITE}/terms`,
        },
        {
          tagName: "link",
          rel: "alternate",
          hrefLang: "en",
          href: `${SITE}/en/terms`,
        },
        {
          tagName: "link",
          rel: "alternate",
          hrefLang: "x-default",
          href: `${SITE}/terms`,
        },
      ])
    )
  })
})
