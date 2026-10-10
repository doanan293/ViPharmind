import { parsePhoneNumberFromString } from "libphonenumber-js/min"
import { z } from "zod"

/** Numbers typed without a country code are Vietnamese. */
export const DEFAULT_PHONE_COUNTRY = "VN"

function parse(value: string) {
  return parsePhoneNumberFromString(value, DEFAULT_PHONE_COUNTRY)
}

/** Accepts local and international input; the parsed value is E.164 ("+84912345678"). */
export function phoneSchema(invalidMessage: string) {
  return z
    .string()
    .trim()
    .refine((value) => parse(value)?.isValid() === true, {
      error: invalidMessage,
    })
    .transform((value) => parse(value)?.number ?? value)
}
