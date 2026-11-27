import { describe, expect, test } from "vitest"

import { NAMESPACES, resources } from "~/i18n/config"

function keysOf(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) {
    return [prefix]
  }
  return Object.entries(value).flatMap(([key, child]) =>
    keysOf(child, prefix === "" ? key : `${prefix}.${key}`)
  )
}

/** Sorts strings in a fixed, locale-independent order so two key lists compare equal. */
function sorted(values: readonly string[]): string[] {
  return values.toSorted((left, right) => left.localeCompare(right, "en"))
}

describe("translation resources", () => {
  test("both languages register every namespace", () => {
    const expected = sorted(NAMESPACES)
    expect(sorted(Object.keys(resources.vi))).toEqual(expected)
    expect(sorted(Object.keys(resources.en))).toEqual(expected)
  })

  test.each(NAMESPACES)("vi and en define the same keys in %s", (namespace) => {
    expect(sorted(keysOf(resources.en[namespace]))).toEqual(
      sorted(keysOf(resources.vi[namespace]))
    )
  })

  test("the product is called ViPharmind everywhere it is named", () => {
    for (const language of ["vi", "en"] as const) {
      expect(resources[language].common.appName).toBe("ViPharmind")
      expect(
        resources[language].landing.meta.title.startsWith("ViPharmind")
      ).toBe(true)
    }
  })
})
