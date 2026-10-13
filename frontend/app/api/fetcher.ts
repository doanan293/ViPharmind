import { toApiError } from "~/api/problem"
import { CSRF_HEADER, readCsrfToken } from "~/lib/csrf"

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"])
/** The UI language, so codes and notices arrive in it. */
function uiLanguage(): string | undefined {
  return document.documentElement.lang || undefined
}

/**
 * orval mutator for every generated request. Requests run only in the browser (route
 * clientLoaders and TanStack Query), so the relative /api URL stays on the page's origin.
 */
export async function fetcher<T>(url: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase()
  const headers = new Headers(init?.headers)
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json, application/problem+json")
  }
  const language = uiLanguage()
  if (language !== undefined && !headers.has("Accept-Language")) {
    headers.set("Accept-Language", language)
  }
  if (UNSAFE_METHODS.has(method)) {
    const token = readCsrfToken()
    if (token !== undefined) {
      headers.set(CSRF_HEADER, token)
    }
  }

  const response = await fetch(url, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  })
  if (!response.ok) {
    throw await toApiError(response)
  }

  // The generated request type decides T; JSON.parse returns `any`, so no type assertion is needed.
  const text = await response.text()
  return JSON.parse(text === "" ? "null" : text)
}
