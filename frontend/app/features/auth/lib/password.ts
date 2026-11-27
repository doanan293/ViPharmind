import { z } from "zod"

/** Passwords entered in the UI; shared by registration and Plan 10's change-password form. */
export const PASSWORD_MIN_LENGTH = 8

/** A password of at least {@link PASSWORD_MIN_LENGTH} characters; `tooShortMessage` is shown otherwise. */
export function passwordSchema(tooShortMessage: string) {
  return z.string().min(PASSWORD_MIN_LENGTH, tooShortMessage)
}
