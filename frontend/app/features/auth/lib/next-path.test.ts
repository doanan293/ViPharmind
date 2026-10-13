import { describe, expect, test } from "vitest"

import { safeNextPath } from "~/features/auth/lib/next-path"

describe("safeNextPath", () => {
  test.each([
    ["/chat/7f0c?draft=1", "/chat/7f0c?draft=1"],
    ["/settings", "/settings"],
    [null, "/chat"],
    [undefined, "/chat"],
    ["", "/chat"],
    ["chat", "/chat"],
    ["https://evil.example/", "/chat"],
    ["//evil.example/", "/chat"],
    ["/\\evil.example", "/chat"],
    ["/\t/evil.example", "/chat"],
    ["/\n/evil.example", "/chat"],
    ["/\r/evil.example", "/chat"],
    ["/settings\u0000", "/chat"],
    ["/settings\u007f", "/chat"],
  ] as const)("%s -> %s", (value, expected) => {
    expect(safeNextPath(value)).toBe(expected)
  })
})
