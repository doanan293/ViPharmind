import { createCookie } from "react-router"
import { z } from "zod"

import { HttpStatus } from "~/api/http-status"
import { SUPPORTED_LANGUAGES } from "~/i18n/config"
import { ONE_YEAR_SECONDS } from "~/lib/time"

/** The httpOnly `lng` cookie that remembers the chosen UI language for a year. */
export const localeCookie = createCookie("lng", {
  path: "/",
  sameSite: "lax",
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  maxAge: ONE_YEAR_SECONDS,
})

const localeForm = z.object({ locale: z.enum(SUPPORTED_LANGUAGES) })

/**
 * Handles the language switcher's form post: sets `localeCookie` to the posted `locale`, or
 * answers 400 with no cookie when it is not a supported language.
 */
export async function setLocale(request: Request): Promise<Response> {
  const parsed = localeForm.safeParse(
    Object.fromEntries(await request.formData())
  )
  if (!parsed.success) {
    return Response.json({ ok: false }, { status: HttpStatus.BAD_REQUEST })
  }
  return Response.json(
    { ok: true },
    {
      headers: {
        "Set-Cookie": await localeCookie.serialize(parsed.data.locale),
      },
    }
  )
}
