import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query"

import { HttpStatus } from "~/api/http-status"
import { isApiError } from "~/api/problem"

type AuthRedirectMeta = { skipAuthRedirect?: boolean }

declare module "@tanstack/react-query" {
  interface Register {
    queryMeta: AuthRedirectMeta
    mutationMeta: AuthRedirectMeta
  }
}

const MAX_RETRIES = 2

/** TanStack Query retry policy: never retry a 4xx `ApiError`, retry anything else up to twice. */
export function shouldRetry(failureCount: number, error: Error): boolean {
  if (isApiError(error) && error.status < HttpStatus.INTERNAL_SERVER_ERROR) {
    return false
  }
  return failureCount < MAX_RETRIES
}

function redirectToLogin(): void {
  const { pathname, search } = window.location
  if (pathname === "/login" || pathname === "/register") {
    return
  }
  window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`)
}

/**
 * Builds the app's QueryClient. `onUnauthorized` runs on any 401 from a query or mutation
 * unless its `meta.skipAuthRedirect` is true. Tests pass their own callback.
 */
export function createQueryClient({
  onUnauthorized,
}: {
  onUnauthorized: () => void
}): QueryClient {
  function reportUnauthorized(
    error: Error,
    meta: AuthRedirectMeta | undefined
  ): void {
    if (
      isApiError(error) &&
      error.status === HttpStatus.UNAUTHORIZED &&
      meta?.skipAuthRedirect !== true
    ) {
      onUnauthorized()
    }
  }

  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        reportUnauthorized(error, query.meta)
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _onMutateResult, mutation) => {
        reportUnauthorized(error, mutation.meta)
      },
    }),
    defaultOptions: {
      queries: { retry: shouldRetry },
    },
  })
}

/** Private routes run only in the browser, so one client lives for the whole tab. */
export const queryClient = createQueryClient({
  onUnauthorized: redirectToLogin,
})
