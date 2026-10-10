import { describe, expect, test } from "vitest"

import { createPasswordSchema, createProfileSchema } from "./account-schemas"

const profile = createProfileSchema({
  required: "required",
  tooLong: "too-long",
})
const passwordMessages = {
  tooShort: "too-short",
  tooLong: "too-long",
  mismatch: "mismatch",
  currentRequired: "current-required",
}
const password = createPasswordSchema(passwordMessages, true)
const firstPassword = createPasswordSchema(passwordMessages, false)

function messagesOf(result: { error?: { issues: { message: string }[] } }) {
  return result.error?.issues.map((issue) => issue.message) ?? []
}

describe("createProfileSchema", () => {
  test("trims the display name", () => {
    expect(profile.parse({ display_name: "  Bác sĩ An  " })).toEqual({
      display_name: "Bác sĩ An",
    })
  })

  test("rejects blank and overlong names", () => {
    expect(messagesOf(profile.safeParse({ display_name: "   " }))).toEqual([
      "required",
    ])
    expect(
      messagesOf(profile.safeParse({ display_name: "a".repeat(101) }))
    ).toEqual(["too-long"])
  })
})

describe("createPasswordSchema", () => {
  test("accepts matching passwords of valid length", () => {
    expect(
      password.safeParse({
        current_password: "mat-khau-cu",
        password: "dai-hon-tam",
        confirm: "dai-hon-tam",
      }).success
    ).toBe(true)
  })

  test("rejects passwords shorter than 8 characters", () => {
    expect(
      messagesOf(
        password.safeParse({
          current_password: "mat-khau-cu",
          password: "1234567",
          confirm: "1234567",
        })
      )
    ).toEqual(["too-short"])
  })

  test("reports a mismatch on the confirm field", () => {
    const result = password.safeParse({
      current_password: "mat-khau-cu",
      password: "dai-hon-tam",
      confirm: "khac-hon-tam",
    })
    expect(messagesOf(result)).toEqual(["mismatch"])
    expect(result.error?.issues[0]?.path).toEqual(["confirm"])
  })

  test("needs the current password only when one is set", () => {
    const withoutCurrent = {
      current_password: "",
      password: "dai-hon-tam",
      confirm: "dai-hon-tam",
    }
    expect(messagesOf(password.safeParse(withoutCurrent))).toEqual([
      "current-required",
    ])
    expect(firstPassword.safeParse(withoutCurrent).success).toBe(true)
  })
})
