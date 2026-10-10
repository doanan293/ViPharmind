import { describe, expect, test } from "vitest"

import { formatList, parseList } from "./lists"

describe("lists", () => {
  test("parses comma-separated text and drops blanks", () => {
    expect(parseList(" a, b ,, c ")).toEqual(["a", "b", "c"])
    expect(parseList("")).toEqual([])
  })

  test("formats a list for editing", () => {
    expect(formatList(["a", "b"])).toBe("a, b")
    expect(formatList(undefined)).toBe("")
  })
})
