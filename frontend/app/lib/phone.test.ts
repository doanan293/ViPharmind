import { describe, expect, test } from "vitest"

import { phoneSchema } from "./phone"

describe("phoneSchema", () => {
  const schema = phoneSchema("invalid")

  test.each(["0912345678", "0912 345 678", "091.234.5678", "+84 91 234 5678"])(
    "%s becomes E.164",
    (input) => {
      expect(schema.parse(input)).toBe("+84912345678")
    }
  )

  test.each(["", "12345", "abc"])("rejects %j", (input) => {
    const result = schema.safeParse(input)
    expect(result.success).toBe(false)
    expect(result.error?.issues[0]?.message).toBe("invalid")
  })
})
