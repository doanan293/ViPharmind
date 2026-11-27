import { parseCookie } from "cookie"

/** Cookie set by the backend CSRF middleware; readable by JavaScript on purpose. */
export const CSRF_COOKIE = "csrftoken"
/** Request header that carries the CSRF token on unsafe methods; the backend compares it with the cookie. */
export const CSRF_HEADER = "x-csrftoken"

/** The CSRF token from its cookie, or undefined during SSR or before the backend has set it. */
export function readCsrfToken(): string | undefined {
  if (typeof document === "undefined") {
    return undefined
  }
  const token = parseCookie(document.cookie)[CSRF_COOKIE]
  return token === "" ? undefined : token
}
