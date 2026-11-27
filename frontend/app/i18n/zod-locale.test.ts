import { afterEach, describe, expect, test } from "vitest"
import { z } from "zod"

import { applyZodLocale } from "~/i18n/zod-locale"

/** The shortest length the probe schema accepts, so "a" is too short. */
const MIN_LENGTH = 3

function tooShortMessage(): string | undefined {
  return z.string().min(MIN_LENGTH).safeParse("a").error?.issues[0]?.message
}

describe("applyZodLocale", () => {
  afterEach(() => {
    applyZodLocale("en")
  })

  test("uses Vietnamese validation messages for vi", () => {
    applyZodLocale("vi")
    expect(tooShortMessage()).toBe("Quá nhỏ: mong đợi string có >=3 ký tự")
  })

  test("uses English validation messages for en", () => {
    applyZodLocale("en")
    expect(tooShortMessage()).toBe(
      "Too small: expected string to have >=3 characters"
    )
  })
})
