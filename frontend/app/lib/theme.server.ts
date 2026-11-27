import { createCookieSessionStorage } from "react-router"
import { createThemeSessionResolver } from "remix-themes"

import { ONE_YEAR_SECONDS } from "~/lib/time"

/** remix-themes resolver backed by the signed, httpOnly `theme` cookie; read it in loaders and the theme action. */
export const themeSessionResolver = createThemeSessionResolver(
  createCookieSessionStorage({
    cookie: {
      name: "theme",
      path: "/",
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: ONE_YEAR_SECONDS,
      // The cookie only holds "light" or "dark". React Router warns about unsigned
      // session cookies, so it is signed; the value is not sensitive.
      secrets: [process.env.THEME_COOKIE_SECRET ?? "vipharmind-theme"],
    },
  })
)
