import { describe, expect, test } from "vitest"

import { pageLabel } from "./citation-format"

const START_PAGE = 812
const END_PAGE = 813

describe("pageLabel", () => {
  test("formats single pages and ranges", () => {
    expect(pageLabel(START_PAGE, END_PAGE)).toEqual({
      key: "pages.range",
      start: START_PAGE,
      end: END_PAGE,
    })
    expect(pageLabel(START_PAGE, START_PAGE)).toEqual({
      key: "pages.single",
      page: START_PAGE,
    })
    expect(pageLabel(START_PAGE, null)).toEqual({
      key: "pages.single",
      page: START_PAGE,
    })
    expect(pageLabel(null, END_PAGE)).toEqual({
      key: "pages.single",
      page: END_PAGE,
    })
    expect(pageLabel(null, null)).toBeNull()
  })
})
